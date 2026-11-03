#!/usr/bin/env python3
"""Vigila los runners del silver y relanza el que se caiga.

Los runners ya saben esperar a que vuelva la cuota y liberar un lote a medias,
pero no sobreviven a su propia muerte: un OOM, un cierre de terminal o un fallo
del CLI los deja fuera sin que nadie se entere hasta horas después. Este
proceso comprueba cada pocos minutos y los vuelve a levantar.

Para solo cuando los tres han terminado su plan, o al superar el tope semanal.

    python scripts/silver_watchdog.py --corpus data/silver/corpus_sinenc.jsonl \
        --sufijo _sinenc --cap-semanal 55
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.filter_runner import weekly_usage  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / ".venv" / "bin" / "python")
JUECES = ("opus", "sonnet", "haiku")


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def vivo(juez: str, sufijo: str) -> bool:
    """Por PID en disco, no por `pgrep -f`.

    `pgrep -f PATRÓN` encuentra cualquier proceso cuya línea de comando
    contenga el patrón — incluido el shell que lanzó el propio pgrep. Eso hizo
    que el watchdog diera por vivo a un runner muerto durante cinco horas.
    """
    pidf = ROOT / "data" / "silver" / f"runner_{juez}{sufijo}.pid"
    if not pidf.exists():
        return False
    try:
        pid = int(pidf.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)          # señal 0: no mata, solo comprueba
    except (ValueError, ProcessLookupError, PermissionError):
        return False
    return True


def votados(juez: str, sufijo: str) -> int:
    f = ROOT / "data" / "silver" / f"votos_{juez}{sufijo}.jsonl"
    if not f.exists():
        return 0
    return sum(1 for x in f.read_text(encoding="utf-8").splitlines() if x.strip())


def levanta(juez: str, corpus: str, sufijo: str, cap: float) -> None:
    logf = ROOT / "data" / "silver" / f"runner_{juez}{sufijo}.log"
    with logf.open("a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] ── relanzado por el watchdog ──\n")
        subprocess.Popen(
            [PYTHON, "-u", str(ROOT / "scripts" / "silver_runner.py"),
             "--juez", juez, "--sufijo", sufijo, "--corpus", corpus,
             "--cap-semanal", str(cap)],
            stdout=f, stderr=subprocess.STDOUT, cwd=ROOT,
            start_new_session=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default="data/silver/corpus_sinenc.jsonl")
    ap.add_argument("--sufijo", default="_sinenc")
    ap.add_argument("--cap-semanal", type=float, default=55.0)
    ap.add_argument("--intervalo", type=float, default=300.0)
    ap.add_argument("--jueces", default=",".join(JUECES),
                    help="a quiénes vigilar; por defecto los tres")
    args = ap.parse_args()

    jueces = tuple(x.strip() for x in args.jueces.split(",") if x.strip())
    total = sum(1 for _ in (ROOT / args.corpus).open(encoding="utf-8"))
    claude_bin = shutil.which("claude") or "claude"
    log(f"vigilando {', '.join(jueces)} sobre {total:,} artículos "
        f"(tope semanal {args.cap_semanal:.0f} %)")

    while True:
        uso = weekly_usage(claude_bin)
        if uso and uso[0] >= args.cap_semanal:
            log(f"⏹ semanal al {uso[0]:.0f} %: no relanzo a nadie más.")
            return 0

        completos = 0
        for j in jueces:
            n = votados(j, args.sufijo)
            if n >= total:
                completos += 1
                continue
            if not vivo(j, args.sufijo):
                log(f"⚠ {j} caído con {n:,}/{total:,}: lo relanzo")
                levanta(j, args.corpus, args.sufijo, args.cap_semanal)
                time.sleep(5)

        if completos == len(jueces):
            log(f"✓ {', '.join(jueces)} completaron {total:,}")
            return 0
        time.sleep(args.intervalo)


if __name__ == "__main__":
    raise SystemExit(main())
