#!/usr/bin/env bash
# Label Studio como SERVICIO de macOS (launchd), igual que collector.sh.
#
# Un solo servidor para los dos anotadores: cada uno entra con su usuario, la
# base de datos es una, y el progreso de ambos se ve en tiempo real. Sobrevive
# al cierre de la terminal y al reinicio del equipo.
#
#   ./scripts/labelstudio_service.sh install [--port 8080] [--public-url https://...]
#   ./scripts/labelstudio_service.sh start | stop | status | logs | uninstall
#
# El registro de usuarios queda cerrado: solo se entra con el enlace de
# invitacion (Organization > Invite people) que genera quien administra.

set -euo pipefail

LABEL="com.ideographco.labelstudio"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LS_BIN="$HOME/label-studio-env/bin/label-studio"
DATA_DIR="$HOME/label-studio-data"
LOG_OUT="$DATA_DIR/label-studio.log"
LOG_ERR="$DATA_DIR/label-studio.error.log"
DOMAIN="gui/$(id -u)"

die() { printf '✗ %s\n' "$1" >&2; exit 1; }
is_registered() { launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; }

cmd_install() {
  local port="8080" public_url=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --port)       port="$2"; shift 2 ;;
      --public-url) public_url="$2"; shift 2 ;;
      *) die "opcion desconocida: $1" ;;
    esac
  done
  [[ -x "$LS_BIN" ]] || die "no existe $LS_BIN (instala: python3 -m venv ~/label-studio-env && ~/label-studio-env/bin/pip install label-studio)"
  mkdir -p "$DATA_DIR" "$HOME/Library/LaunchAgents"

  # LABEL_STUDIO_HOST hace que los enlaces absolutos (invitaciones, export)
  # apunten a la URL por la que entra Juan, no a localhost.
  local host_line=""
  [[ -n "$public_url" ]] && host_line="    <key>LABEL_STUDIO_HOST</key><string>${public_url}</string>"

  # OJO: heredoc SIN comillas para expandir variables -> nada de acentos
  # graves aqui dentro, se ejecutarian como comandos.
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${LS_BIN}</string>
    <string>start</string>
    <string>--port</string><string>${port}</string>
    <string>--no-browser</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>LABEL_STUDIO_BASE_DATA_DIR</key><string>${DATA_DIR}</string>
    <key>LABEL_STUDIO_DISABLE_SIGNUP_WITHOUT_LINK</key><string>true</string>
${host_line}
    <key>PATH</key><string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key><string>${HOME}</string>
  </dict>
  <key>WorkingDirectory</key><string>${DATA_DIR}</string>
  <key>StandardOutPath</key><string>${LOG_OUT}</string>
  <key>StandardErrorPath</key><string>${LOG_ERR}</string>
  <!-- Servidor: debe estar siempre arriba. Arranca al iniciar sesion y se
       relanza si muere, con 30 s de freno para no ciclar. -->
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
</dict>
</plist>
PLIST_EOF
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  echo "✓ Configuracion guardada: $LABEL"
  echo "  puerto      $port"
  echo "  datos       $DATA_DIR"
  echo "  URL publica ${public_url:-(ninguna: solo http://localhost:$port)}"
  echo "  registro    cerrado (solo con enlace de invitacion)"
  echo
  echo "Arrancar:  ./scripts/labelstudio_service.sh start"
}

cmd_start() {
  [[ -f "$PLIST" ]] || die "no instalado. Corre: ./scripts/labelstudio_service.sh install"
  if is_registered; then
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    local w=0; while is_registered && (( w < 15 )); do sleep 1; w=$((w+1)); done
  fi
  launchctl bootstrap "$DOMAIN" "$PLIST" || die "launchd rechazo el servicio (revisa $PLIST)"
  local w=0 code=""
  while (( w < 45 )); do
    code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null || true)
    [[ "$code" == "200" || "$code" == "302" ]] && break
    sleep 2; w=$((w+2))
  done
  [[ "$code" == "200" || "$code" == "302" ]] || die "arranco pero no responde en 45 s. Revisa $LOG_ERR"
  echo "✓ Label Studio corriendo en http://localhost:8080 (servicio $LABEL)"
}

cmd_stop() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  echo "⏸  Label Studio detenido. Reanudar: ./scripts/labelstudio_service.sh start"
}

cmd_status() {
  echo "servicio  : $LABEL"
  if is_registered; then
    local pid state
    pid=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tpid =/{print $3}')
    state=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tstate =/{print $3}')
    echo "estado    : registrado (state=${state:-?} pid=${pid:-ninguno})"
    [[ "${state:-}" == "running" ]] && echo "            ▶ ARRIBA" || echo "            ⏸ detenido"
  else
    echo "estado    : no registrado"
  fi
  local code; code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/ 2>/dev/null || true)
  echo "http      : ${code:-sin respuesta} en http://localhost:8080"
  echo "escucha   : $(lsof -nP -i :8080 -sTCP:LISTEN 2>/dev/null | tail -n +2 | awk '{print $9}' | sort -u | tr '\n' ' ')"
  echo "datos     : $DATA_DIR"
}

cmd_logs() { touch "$LOG_OUT"; tail -f "$LOG_OUT"; }

cmd_uninstall() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  echo "✓ Servicio desinstalado. Los datos siguen en $DATA_DIR."
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
Label Studio como servicio de macOS (launchd).

  ./scripts/labelstudio_service.sh install [--port 8080] [--public-url https://...]
  ./scripts/labelstudio_service.sh start | stop | status | logs | uninstall
USAGE
    ;;
esac
