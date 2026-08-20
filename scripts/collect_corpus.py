"""Recolección por rondas hasta alcanzar un objetivo de artículos.

El scraper es INCREMENTAL: la base de dedup (`data/scraper_history.db`)
registra cada URL descargada, así que volver a correrlo nunca re-descarga lo
que ya tienes. Este script explota eso para llegar a corpus grandes sin
supervisar: corre rondas cortas, informa progreso y para al llegar al
objetivo.

**Se interrumpe y se reanuda sin perder nada.** Ctrl+C, el portátil que se
suspende, un corte de luz: vuelves a lanzar el MISMO comando y continúa
donde quedó. Cada artículo se escribe a disco antes de marcarse en la BD, así
que una interrupción no deja ni duplicados ni URLs "quemadas".

Uso:
    # arrancar (o reanudar) hacia 40.000 artículos
    python scripts/collect_corpus.py --target 40000

    # en macOS, evitando que el equipo se suspenda:
    caffeinate -is python scripts/collect_corpus.py --target 40000

    # dejarlo corriendo aunque cierres la terminal:
    nohup caffeinate -is python scripts/collect_corpus.py --target 40000 \\
        > logs/collect.log 2>&1 &
    tail -f logs/collect.log

Consultar el progreso en cualquier momento (incluso mientras corre):
    wc -l data/raw/articles.jsonl
"""

import argparse
import logging
import signal
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import LOGS_DIR, RAW_DIR  # noqa: E402
from src.scraper.pipeline import scrape_pipeline  # noqa: E402
from src.scraper.prefilter import try_load_prefilter  # noqa: E402
from src.scraper.sources import SOURCES  # noqa: E402

logger = logging.getLogger("collect_corpus")


def count_articles(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def human(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recolecta artículos por rondas hasta alcanzar el objetivo",
    )
    parser.add_argument("--target", type=int, default=40000,
                        help="Artículos totales deseados (default: 40000)")
    parser.add_argument("--per-round", type=int, default=10,
                        help="Artículos por fuente en cada ronda (default: 10). "
                             "Bajo a propósito: rondas cortas dan progreso "
                             "visible y reparten el cupo entre las 434 fuentes")
    parser.add_argument("--workers", type=int, default=6,
                        help="Fuentes en paralelo (default: 6)")
    parser.add_argument("--max-rounds", type=int, default=200)
    parser.add_argument("--rate-limit", type=float, default=4.5,
                        help="Segundos entre llamadas al LLM (4.5 = free tier)")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash-lite")
    parser.add_argument("--min-chars", type=int, default=800)
    parser.add_argument("--prefilter", nargs="?", const="__default__", default=None,
                        help="Usa el prefilter local. NO en la primera corrida: "
                             "necesita que el filtro LLM genere primero su log")
    parser.add_argument("--categories", nargs="+", default=None,
                        help="Limitar a estas categorías de fuente")
    parser.add_argument("--stop-after-empty", type=int, default=3,
                        help="Parar tras N rondas consecutivas sin artículos "
                             "nuevos (fuentes agotadas). Default: 3")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    # launchd manda SIGTERM al pausar el servicio: tratarlo como Ctrl+C para
    # que se imprima el resumen y la ronda en curso cierre ordenada.
    signal.signal(
        signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    output_path = RAW_DIR / "articles.jsonl"
    filter_log = LOGS_DIR / "filter_decisions.jsonl"
    filter_log.parent.mkdir(parents=True, exist_ok=True)

    sources = SOURCES
    if args.categories:
        sources = {k: v for k, v in SOURCES.items() if v["category"] in args.categories}

    import os

    from dotenv import load_dotenv
    from google import genai

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("✗ Falta GEMINI_API_KEY en .env")
    client = genai.Client(api_key=api_key)

    prefilter = None
    if args.prefilter:
        path = (
            "data/models/prefilter.joblib" if args.prefilter == "__default__"
            else args.prefilter
        )
        prefilter = try_load_prefilter(path)

    start_count = count_articles(output_path)
    started = time.time()

    print("=" * 66)
    print("  RECOLECCIÓN POR RONDAS")
    print(f"  Objetivo:        {args.target:,} artículos")
    print(f"  Ya tienes:       {start_count:,}")
    print(f"  Faltan:          {max(0, args.target - start_count):,}")
    print(f"  Fuentes:         {len(sources)}")
    print(f"  Por ronda:       {args.per_round}/fuente · {args.workers} workers")
    print(f"  Prefilter:       {'SÍ' if prefilter else 'NO'}")
    print("=" * 66)
    print("  Interrumpible: Ctrl+C y relanzar el mismo comando continúa.")
    print()

    if start_count >= args.target:
        print(f"✓ Objetivo ya alcanzado ({start_count:,} ≥ {args.target:,}).")
        return

    empty_streak = 0
    try:
        for round_num in range(1, args.max_rounds + 1):
            before = count_articles(output_path)
            if before >= args.target:
                break

            round_started = time.time()
            print(f"── Ronda {round_num}  ({before:,}/{args.target:,})", flush=True)

            scrape_pipeline(
                sources=sources,
                output_path=output_path,
                max_per_source=args.per_round,
                use_llm_filter=True,
                llm_client=client,
                llm_model=args.model,
                min_chars=args.min_chars,
                rate_limit_filter=args.rate_limit,
                filter_log_path=filter_log,
                prefilter=prefilter,
                workers=args.workers,
            )

            after = count_articles(output_path)
            added = after - before
            elapsed = time.time() - round_started
            total_elapsed = time.time() - started
            gained = after - start_count
            rate = gained / total_elapsed if total_elapsed > 0 else 0
            remaining = max(0, args.target - after)
            if remaining == 0:
                eta = "objetivo alcanzado"
            elif rate > 0:
                eta = human(remaining / rate)
            else:
                eta = "?"

            print(f"   +{added} en {human(elapsed)}  |  total {after:,}  "
                  f"|  ritmo {rate * 3600:.0f}/h  |  ETA {eta}", flush=True)

            if added == 0:
                empty_streak += 1
                if empty_streak >= args.stop_after_empty:
                    print(f"\n⚠ {empty_streak} rondas sin artículos nuevos: las "
                          "fuentes dieron todo lo que tenían con este cupo.")
                    print("  Opciones: subir --per-round, o añadir fuentes.")
                    break
            else:
                empty_streak = 0

    except KeyboardInterrupt:
        print("\n\n⏸  Interrumpido por el usuario.")

    final = count_articles(output_path)
    print()
    print("=" * 66)
    print(f"  Artículos: {final:,}  (+{final - start_count:,} en esta sesión)")
    print(f"  Tiempo:    {human(time.time() - started)}")
    print(f"  Salida:    {output_path}")
    if final < args.target:
        print(f"\n  Para continuar hacia {args.target:,}, relanza el mismo comando:")
        print(f"    python scripts/collect_corpus.py --target {args.target}")
    else:
        print("\n  ✓ Objetivo alcanzado. Siguiente paso:")
        print("    python scripts/label.py            # etiquetado silver")
        print("    dvc add data/raw                   # versionar el corpus")
    print("=" * 66)


if __name__ == "__main__":
    main()
