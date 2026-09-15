#!/usr/bin/env bash
# Tunel publico para que el otro anotador llegue al Label Studio de este Mac.
#
# Usa un "quick tunnel" de Cloudflare: no pide cuenta ni permisos de
# administrador. A cambio, la URL CAMBIA cada vez que el tunel se reinicia,
# asi que el servicio la escribe en un archivo y reconfigura Label Studio
# solo (LABEL_STUDIO_HOST hace falta para CSRF y enlaces absolutos).
#
#   ./scripts/tunnel_service.sh install | start | stop | status | url | logs
#
# Seguridad: la URL es publica, pero Label Studio exige login y el registro
# abierto esta cerrado (solo por enlace de invitacion).

set -euo pipefail

LABEL="com.ideographco.tunnel"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
DATA_DIR="$HOME/label-studio-data"
LOG_OUT="$DATA_DIR/tunnel.log"
URL_FILE="$DATA_DIR/tunnel_url.txt"
PYTHON="$ROOT/.venv/bin/python"
RUNNER="$ROOT/scripts/tunnel_runner.py"
DOMAIN="gui/$(id -u)"

die() { printf '✗ %s\n' "$1" >&2; exit 1; }
is_registered() { launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; }

cmd_install() {
  command -v cloudflared >/dev/null || die "falta cloudflared (brew install cloudflared)"
  mkdir -p "$DATA_DIR" "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>${LABEL}</string>
  <!-- Con el python del venv, NO con /bin/bash: launchd no le concede a bash
       acceso al Escritorio (TCC de macOS) y el servicio moria con
       "Operation not permitted". -->
  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${RUNNER}</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>HOME</key><string>${HOME}</string>
  </dict>
  <key>WorkingDirectory</key><string>${DATA_DIR}</string>
  <key>StandardOutPath</key><string>${LOG_OUT}</string>
  <key>StandardErrorPath</key><string>${LOG_OUT}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
</dict>
</plist>
PLIST_EOF
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  echo "✓ Configuracion guardada: $LABEL"
  echo "  URL se publica en: $URL_FILE"
  echo
  echo "Arrancar:  ./scripts/tunnel_service.sh start"
}

cmd_start() {
  [[ -f "$PLIST" ]] || die "no instalado. Corre: ./scripts/tunnel_service.sh install"
  pkill -f "cloudflared tunnel --url" 2>/dev/null || true
  if is_registered; then
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    local w=0; while is_registered && (( w < 15 )); do sleep 1; w=$((w+1)); done
  fi
  : > "$URL_FILE"
  launchctl bootstrap "$DOMAIN" "$PLIST" || die "launchd rechazo el servicio"
  local w=0
  while (( w < 60 )); do
    [[ -s "$URL_FILE" ]] && break
    sleep 2; w=$((w+2))
  done
  [[ -s "$URL_FILE" ]] || die "el tunel no publico URL en 60 s. Revisa $LOG_OUT"
  echo "✓ Tunel arriba"
  cmd_url
}

cmd_stop() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
  pkill -f "cloudflared tunnel --url" 2>/dev/null || true
  echo "⏸  Tunel cerrado. Label Studio sigue accesible en http://localhost:8080"
}

cmd_url() {
  [[ -s "$URL_FILE" ]] || die "no hay URL todavia. Arranca: ./scripts/tunnel_service.sh start"
  local url; url=$(cat "$URL_FILE")
  local token
  token=$("$HOME/label-studio-env/bin/python" - <<PY
import sqlite3, os
db = os.path.expanduser("~/label-studio-data/label_studio.sqlite3")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
print(con.execute("SELECT token FROM organization LIMIT 1").fetchone()[0])
PY
)
  echo "  Para anotar   : $url"
  echo "  Invitar a Juan: $url/user/signup/?token=$token"
}

cmd_status() {
  echo "servicio  : $LABEL"
  if is_registered; then
    local state; state=$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null | awk '/^\tstate =/{print $3}')
    [[ "${state:-}" == "running" ]] && echo "estado    : ▶ ARRIBA" || echo "estado    : ⏸ ${state:-detenido}"
  else
    echo "estado    : no registrado"
  fi
  [[ -s "$URL_FILE" ]] && cmd_url || echo "  (sin URL)"
}

cmd_logs() { touch "$LOG_OUT"; tail -f "$LOG_OUT"; }

case "${1:-}" in
  install) cmd_install ;;
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  status)  cmd_status ;;
  url)     cmd_url ;;
  logs)    cmd_logs ;;
  *) cat <<USAGE
Tunel publico para el Label Studio compartido.

  ./scripts/tunnel_service.sh install | start | stop | status | url | logs

OJO: la URL cambia en cada arranque. Tras un reinicio, pasale a Juan la nueva
con: ./scripts/tunnel_service.sh url
USAGE
  ;;
esac
