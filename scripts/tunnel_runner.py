"""Levanta el túnel público y mantiene a Label Studio al corriente de su URL.

Lo ejecuta launchd (ver `tunnel_service.sh`); no se llama a mano.

Va en Python y no en bash a propósito: launchd no le concede a /bin/bash
acceso al Escritorio (TCC de macOS) y el servicio moría con "Operation not
permitted", mientras que el intérprete del venv sí lo tiene.

El "quick tunnel" de Cloudflare no pide cuenta ni permisos de administrador,
pero asigna un dominio distinto en cada arranque. Por eso aquí se publica la
URL en un archivo y se reconfigura Label Studio cuando cambia: sin
LABEL_STUDIO_HOST correcto, Django rechaza los formularios por CSRF y los
enlaces de invitación apuntan a localhost.
"""

import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path.home() / "label-studio-data"
URL_FILE = DATA_DIR / "tunnel_url.txt"
RAW_LOG = DATA_DIR / "cloudflared.log"
LS_SERVICE = ROOT / "scripts" / "labelstudio_service.sh"
LS_LABEL = "com.ideographco.labelstudio"

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_tunnel: subprocess.Popen | None = None


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def _shutdown(*_):
    if _tunnel and _tunnel.poll() is None:
        _tunnel.terminate()
    sys.exit(0)


def current_ls_host() -> str | None:
    """Host público con el que Label Studio está corriendo ahora mismo."""
    out = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{LS_LABEL}"],
        capture_output=True, text=True,
    ).stdout
    m = re.search(r"LABEL_STUDIO_HOST\s*=>\s*(\S+)", out)
    return m.group(1) if m else None


def main() -> int:
    global _tunnel
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cloudflared = "/opt/homebrew/bin/cloudflared"
    if not Path(cloudflared).exists():
        import shutil
        cloudflared = shutil.which("cloudflared") or ""
    if not cloudflared:
        log("✗ falta cloudflared (brew install cloudflared)")
        return 1

    with open(RAW_LOG, "w", encoding="utf-8") as raw:
        _tunnel = subprocess.Popen(
            [cloudflared, "tunnel", "--url", "http://localhost:8080",
             "--no-autoupdate"],
            stdout=raw, stderr=subprocess.STDOUT,
        )

    url = ""
    for _ in range(60):
        if _tunnel.poll() is not None:
            log(f"✗ cloudflared murió (código {_tunnel.returncode})")
            return 1
        try:
            m = _URL_RE.search(RAW_LOG.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            m = None
        if m:
            url = m.group(0)
            break
        time.sleep(2)

    if not url:
        log("✗ cloudflared no publicó URL en 120 s")
        _tunnel.terminate()
        return 1

    URL_FILE.write_text(url + "\n", encoding="utf-8")
    log(f"URL pública: {url}")

    # Solo se reinicia Label Studio si el host cambió: reinstalarlo siempre
    # cortaría la sesión de quien esté anotando en ese momento.
    if current_ls_host() != url:
        log(f"reconfigurando Label Studio (host → {url})")
        for args in (["install", "--port", "8080", "--public-url", url], ["start"]):
            result = subprocess.run(["/bin/bash", str(LS_SERVICE), *args],
                                    capture_output=True, text=True, cwd=ROOT)
            if result.returncode != 0:
                log(f"   ⚠ labelstudio_service.sh {args[0]}: "
                    f"{(result.stderr or result.stdout)[:200]}")
    else:
        log("Label Studio ya apuntaba a esta URL")

    _tunnel.wait()
    log("cloudflared terminó")
    return 1      # KeepAlive lo relanza y se pedirá una URL nueva


if __name__ == "__main__":
    sys.exit(main())
