#!/usr/bin/env bash
# Corre la recolección como SERVICIO de macOS (launchd).
#
# Sobrevive al cierre de la terminal y al reinicio del equipo, y se reinicia
# solo si el proceso se cae. Como el scraper es incremental (la base de dedup
# recuerda cada URL), un reinicio simplemente continúa donde iba.
#
#   ./scripts/collector.sh install [--target N] [--prefilter] [--rate-limit S]
#   ./scripts/collector.sh start | stop | status | logs | uninstall
#
# `stop` pausa la recolección; `start` la retoma sin perder nada.

set -euo pipefail

LABEL="com.ideographco.collector"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_OUT="$ROOT/logs/collector.log"
LOG_ERR="$ROOT/logs/collector.error.log"
PYTHON="$ROOT/.venv/bin/python"
DOMAIN="gui/$(id -u)"

die() { printf '✗ %s\n' "$1" >&2; exit 1; }

corpus_count() {
  local f="$ROOT/data/raw/articles.jsonl"
  [[ -f "$f" ]] && wc -l < "$f" | tr -d ' ' || echo 0
}

cmd_install() {
  local target=40000 prefilter="" rate="4.5" workers="6" per_round="10"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --target)     target="$2"; shift 2 ;;
      --rate-limit) rate="$2"; shift 2 ;;
      --workers)    workers="$2"; shift 2 ;;
      --per-round)  per_round="$2"; shift 2 ;;
      --prefilter)  prefilter="yes"; shift ;;
      *) die "opción desconocida: $1" ;;
    esac
  done

  [[ -x "$PYTHON" ]] || die "no existe $PYTHON (¿creaste el venv?)"
  mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

  # Los argumentos van uno por línea en el plist.
  local extra=""
  [[ -n "$prefilter" ]] && extra="    <string>--prefilter</string>"

  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>

  <!-- caffeinate -is: evita que el equipo entre en reposo mientras recolecta -->
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-is</string>
    <string>${PYTHON}</string>
    <string>${ROOT}/scripts/collect_corpus.py</string>
    <string>--target</string><string>${target}</string>
    <string>--per-round</string><string>${per_round}</string>
    <string>--workers</string><string>${workers}</string>
    <string>--rate-limit</string><string>${rate}</string>
${extra}
  </array>

  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>StandardOutPath</key><string>${LOG_OUT}</string>
  <key>StandardErrorPath</key><string>${LOG_ERR}</string>

  <!-- No arranca solo al iniciar sesión: tú decides cuándo con 'start'. -->
  <key>RunAtLoad</key><false/>

  <!-- Reinicia SOLO si el proceso muere con error. Si termina bien (objetivo
       alcanzado) no lo relanza. El reinicio es seguro: el dedup persistente
       hace que continúe en vez de repetir. -->
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>

  <key>ThrottleInterval</key><integer>60</integer>
  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
</dict>
</plist>
PLIST_EOF

  # `install` SOLO escribe la configuración. Registrarla aquí haría que
  # launchd arrancase el trabajo de inmediato (KeepAlive lo levanta aunque
  # RunAtLoad sea false), y el arranque debe ser una decisión explícita.
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

  echo "✓ Configuración guardada: $LABEL"
  echo "  objetivo   $target artículos"
  echo "  por ronda  $per_round/fuente · $workers workers · rate ${rate}s"
  echo "  prefilter  ${prefilter:-no}"
  echo "  logs       $LOG_OUT"
  echo
  echo "Arrancar:  ./scripts/collector.sh start"
}

cmd_start() {
  [[ -f "$PLIST" ]] || die "no instalado. Corre: ./scripts/collector.sh install"
  # Registrar de cero: `bootout` limpia cualquier estado previo (rancio tras
  # un stop o un crash) y `bootstrap` registra Y arranca — con KeepAlive
  # activo launchd levanta el trabajo al registrarlo, sin kickstart.
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null \
    || launchctl load -w "$PLIST" 2>/dev/null \
    || die "no se pudo arrancar el servicio"
  echo "✓ Recolectando en segundo plano. Ya puedes cerrar la terminal."
  echo "  seguir el avance:  ./scripts/collector.sh logs"
  echo "  pausar:            ./scripts/collector.sh stop"
}

cmd_stop() {
  # bootout detiene el proceso Y evita que KeepAlive lo relance.
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null \
    || launchctl stop "$LABEL" 2>/dev/null \
    || true
  echo "⏸  Pausado con $(corpus_count) artículos recolectados."
  echo "   Reanudar (continúa donde iba):  ./scripts/collector.sh start"
}

cmd_status() {
  echo "servicio  : $LABEL"
  if launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    local pid state
    pid=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tpid =/{print $3}')
    state=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tstate =/{print $3}')
    echo "estado    : registrado (state=${state:-?} pid=${pid:-ninguno})"
    # El pid queda en el registro aunque el proceso ya murió: lo que decide
    # si está vivo es state=running, no la presencia del pid.
    if [[ "${state:-}" == "running" ]]; then
      echo "            ▶ CORRIENDO"
    else
      echo "            ⏸ detenido"
    fi
  else
    echo "estado    : no registrado"
  fi
  echo "artículos : $(corpus_count)"
  local flog="$ROOT/logs/filter_decisions.jsonl"
  if [[ -f "$flog" ]]; then
    local n; n=$(wc -l < "$flog" | tr -d ' ')
    echo "filtro    : $n decisiones"
    if (( n >= 2000 )); then
      echo "            → ya puedes entrenar el prefilter:"
      echo "              ./scripts/collector.sh stop"
      echo "              .venv/bin/python scripts/train_prefilter.py"
      echo "              ./scripts/collector.sh install --prefilter && ./scripts/collector.sh start"
    fi
  fi
  if [[ -s "$LOG_ERR" ]]; then
    # `grep -c` sale con 1 cuando no hay coincidencias: con `|| echo 0` se
    # concatenaba un segundo cero y la comparación aritmética fallaba.
    local reales
    reales=$(grep -cE "Traceback|CRITICAL|SystemExit|Errno" "$LOG_ERR" 2>/dev/null) || reales=0
    if (( reales > 0 )); then
      echo "ERRORES   : $reales reales en $LOG_ERR — revísalo"
    else
      echo "avisos    : $(wc -l < "$LOG_ERR" | tr -d ' ') en $LOG_ERR"
      echo "            (timeouts de sitemap y pool de conexiones: normales)"
    fi
  fi
  echo
  echo "últimas líneas del log:"
  [[ -f "$LOG_OUT" ]] && tail -6 "$LOG_OUT" | sed 's/^/  /' || echo "  (sin log todavía)"
}

cmd_logs() { touch "$LOG_OUT"; tail -f "$LOG_OUT"; }

cmd_uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ Servicio desinstalado (los datos y logs se conservan)."
}

case "${1:-}" in
  install)   shift; cmd_install "$@" ;;
  start)     cmd_start ;;
  stop)      cmd_stop ;;
  status)    cmd_status ;;
  logs)      cmd_logs ;;
  uninstall) cmd_uninstall ;;
  *)
    cat <<USAGE
Recolección como servicio de macOS (launchd).

  ./scripts/collector.sh install [--target N] [--per-round N] [--workers N]
                                 [--rate-limit S] [--prefilter]
  ./scripts/collector.sh start       arrancar / reanudar
  ./scripts/collector.sh stop        pausar
  ./scripts/collector.sh status      progreso y estado
  ./scripts/collector.sh logs        seguir el log en vivo (Ctrl+C para salir)
  ./scripts/collector.sh uninstall   quitar el servicio

Pausar y reanudar no pierde nada: el dedup persistente hace que continúe.
USAGE
    ;;
esac
