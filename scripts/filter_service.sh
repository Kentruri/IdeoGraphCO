#!/usr/bin/env bash
# Corre el FILTRADO como servicio de macOS (launchd), igual que collector.sh
# hacía con el scraping.
#
# Sobrevive al cierre de la terminal, y `caffeinate -is` impide que el equipo
# se duerma mientras trabaja. Como el cursor es persistente, pausar y reanudar
# no pierde ni repite ningún artículo.
#
#   ./scripts/filter_service.sh install [--model opus|sonnet] [--cooldown S]
#   ./scripts/filter_service.sh start | stop | status | logs | uninstall

set -euo pipefail

LABEL="com.ideographco.filter"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_OUT="$ROOT/logs/filter.log"
LOG_ERR="$ROOT/logs/filter.error.log"
PYTHON="$ROOT/.venv/bin/python"
DOMAIN="gui/$(id -u)"

die() { printf '✗ %s\n' "$1" >&2; exit 1; }

progress() {
  "$PYTHON" "$ROOT/scripts/agent_filter.py" status --json 2>/dev/null || echo '{}'
}

cmd_install() {
  # 4,5 h = la ventana del límite de uso. Si el mensaje anuncia la hora
  # exacta de renovación, el runner la usa y despierta antes.
  local model="opus" cooldown="60" quota_wait="16200" stalls="3"
  local transient_wait="300" weekly_stop="80" min_corpus="40000"
  local collect_extra="0" stop_on_limit="" weekly_wait=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --model)      model="$2"; shift 2 ;;
      --cooldown)   cooldown="$2"; shift 2 ;;
      --quota-wait) quota_wait="$2"; shift 2 ;;
      --transient-wait) transient_wait="$2"; shift 2 ;;
      --weekly-stop) weekly_stop="$2"; shift 2 ;;
      --min-corpus)  min_corpus="$2"; shift 2 ;;
      --collect-extra) collect_extra="$2"; shift 2 ;;
      --stop-on-session) stop_on_limit="1"; shift ;;
      --stop-on-limit)   stop_on_limit="1"; shift ;;   # alias antiguo
      --weekly-wait)     weekly_wait="1"; shift ;;
      --max-stalls) stalls="$2"; shift 2 ;;
      *) die "opción desconocida: $1" ;;
    esac
  done

  [[ -x "$PYTHON" ]] || die "no existe $PYTHON (¿creaste el venv?)"
  local claude_bin; claude_bin="$(command -v claude)" \
    || die "no encuentro el binario 'claude' en el PATH"
  mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

  # launchd arranca con un PATH mínimo: node (y por tanto claude) no estaría.
  # Se fija el directorio del binario encontrado ahora, en el shell del usuario.
  local claude_dir; claude_dir="$(dirname "$claude_bin")"

  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>

  <!-- El runner va con el python del venv, NO con /bin/bash: launchd no le
       concede a bash acceso al Escritorio (TCC de macOS) y el servicio moría
       con "Operation not permitted". El intérprete del venv sí lo tiene.
       OJO: este heredoc NO va entrecomillado (hace falta expandir las
       variables), asi que aqui dentro las tildes invertidas se ejecutan como
       comandos. Nada de acentos graves en estos comentarios.
       El proceso ya no va envuelto en caffeinate: lo lanza y lo suelta el
       propio runner, para no tener el Mac despierto en una espera de dias. -->
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${ROOT}/scripts/filter_runner.py</string>
  </array>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>${claude_dir}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>CLAUDE_BIN</key><string>${claude_bin}</string>
    <key>FILTER_MODEL</key><string>${model}</string>
    <key>FILTER_COOLDOWN</key><string>${cooldown}</string>
    <key>FILTER_QUOTA_WAIT</key><string>${quota_wait}</string>
    <key>FILTER_TRANSIENT_WAIT</key><string>${transient_wait}</string>
    <key>FILTER_WEEKLY_STOP_PCT</key><string>${weekly_stop}</string>
    <key>FILTER_MIN_CORPUS</key><string>${min_corpus}</string>
    <key>FILTER_COLLECT_EXTRA</key><string>${collect_extra}</string>
    <key>FILTER_STOP_ON_SESSION_LIMIT</key><string>${stop_on_limit}</string>
    <key>FILTER_WEEKLY_WAIT</key><string>${weekly_wait}</string>
    <key>FILTER_MAX_STALLS</key><string>${stalls}</string>
    <key>HOME</key><string>${HOME}</string>
  </dict>

  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>StandardOutPath</key><string>${LOG_OUT}</string>
  <key>StandardErrorPath</key><string>${LOG_ERR}</string>

  <!-- No arranca solo al iniciar sesión: tú decides cuándo con 'start'. -->
  <key>RunAtLoad</key><false/>

  <!-- El runner sale con 0 al terminar el corpus y con 1 cuando algo va mal.
       KeepAlive solo relanza el fallo, y con 5 min de freno: si el problema
       persiste (cuota, error), reintentar en bucle solo lo empeora. -->
  <key>KeepAlive</key>
  <dict><key>SuccessfulExit</key><false/></dict>
  <key>ThrottleInterval</key><integer>300</integer>

  <key>ProcessType</key><string>Background</string>
  <key>LowPriorityIO</key><true/>
</dict>
</plist>
PLIST_EOF

  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true

  echo "✓ Configuración guardada: $LABEL"
  echo "  modelo      $model"
  echo "  claude      $claude_bin"
  echo "  pausa       ${cooldown}s entre tandas"
  if [[ -n "$weekly_wait" ]]; then
    echo "  al ${weekly_stop}% sem. espera a que renueve la semana"
  else
    echo "  al ${weekly_stop}% sem. TERMINA el servicio"
  fi
  if [[ -n "$stop_on_limit" ]]; then
    echo "  sin sesion  TERMINA el servicio (no espera la renovacion)"
  else
    echo "  sin sesion  espera y sigue (hasta la hora que anuncie el aviso)"
  fi
  echo "  pasajero    ${transient_wait}s si es sobrecarga"

  echo "  mínimo      ${min_corpus} filtrados; si no llega, arranca el scraping solo"
  if [[ "$collect_extra" != "0" ]]; then
    echo "  reposición  ${collect_extra} crudos nuevos (cantidad fija)"
  else
    echo "  reposición  la calculada segun la tasa de conservacion"
  fi
  echo "  logs        $LOG_OUT"
  echo
  echo "Arrancar:  ./scripts/filter_service.sh start"
}

is_registered() { launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; }

cmd_start() {
  [[ -f "$PLIST" ]] || die "no instalado. Corre: ./scripts/filter_service.sh install"

  # bootout es ASÍNCRONO: un bootstrap inmediato falla en silencio.
  if is_registered; then
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    local waited=0
    while is_registered && (( waited < 15 )); do sleep 1; waited=$((waited + 1)); done
  fi

  launchctl bootstrap "$DOMAIN" "$PLIST" \
    || die "launchd rechazó el servicio (revisa $PLIST)"

  local waited=0 pid=""
  while (( waited < 15 )); do
    pid=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tpid =/{print $3}')
    [[ -n "$pid" ]] && break
    sleep 1; waited=$((waited + 1))
  done
  [[ -n "$pid" ]] || die "el servicio se registró pero no hay proceso. Revisa $LOG_ERR"

  echo "✓ Filtrando en segundo plano (pid $pid). Ya puedes cerrar la terminal."
  echo "  seguir el avance:  ./scripts/filter_service.sh logs"
  echo "  pausar:            ./scripts/filter_service.sh stop"
}

cmd_stop() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null \
    || launchctl stop "$LABEL" 2>/dev/null || true
  echo "⏸  Pausado."
  "$PYTHON" "$ROOT/scripts/agent_filter.py" status 2>/dev/null | sed -n '4,8p'
  echo "   Reanudar (continúa donde iba):  ./scripts/filter_service.sh start"
}

cmd_status() {
  echo "servicio  : $LABEL"
  if is_registered; then
    local pid state
    pid=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tpid =/{print $3}')
    state=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tstate =/{print $3}')
    echo "estado    : registrado (state=${state:-?} pid=${pid:-ninguno})"
    # El pid sobrevive al proceso en el registro: manda state=running.
    if [[ "${state:-}" == "running" ]]; then echo "            ▶ FILTRANDO"
    else echo "            ⏸ detenido"; fi
  else
    echo "estado    : no registrado"
  fi
  echo
  "$PYTHON" "$ROOT/scripts/agent_filter.py" status
  echo
  echo "últimas líneas del log:"
  [[ -f "$LOG_OUT" ]] && tail -12 "$LOG_OUT" | sed 's/^/  /' || echo "  (sin log todavía)"
}

cmd_logs() { touch "$LOG_OUT"; tail -f "$LOG_OUT"; }

cmd_uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ Servicio desinstalado (decisiones y logs se conservan)."
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
Filtrado del corpus como servicio de macOS (launchd).

  ./scripts/filter_service.sh install [--model opus|sonnet] [--cooldown S]
                                      [--quota-wait S] [--transient-wait S]
                                      [--weekly-stop PCT] [--min-corpus N]
                                      [--collect-extra N] [--stop-on-session]
                                      [--weekly-wait]
  ./scripts/filter_service.sh start       arrancar / reanudar
  ./scripts/filter_service.sh stop        pausar
  ./scripts/filter_service.sh status      progreso y estado
  ./scripts/filter_service.sh logs        seguir el log en vivo
  ./scripts/filter_service.sh uninstall   quitar el servicio

Pausar y reanudar no pierde nada: el cursor solo avanza al ingerir un lote.
USAGE
    ;;
esac
