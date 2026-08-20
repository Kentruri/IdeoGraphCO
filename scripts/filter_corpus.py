"""Filtra un corpus YA recolectado: politicidad + colombianidad + limpieza.

Permite separar las dos fases que consumen recursos distintos:

  1. Recolectar sin API   → `collect_corpus.py --no-filter` (red, horas)
  2. Filtrar aparte       → este script (API de Gemini, reanudable)

Ventaja sobre filtrar en línea: con el corpus ya en disco puedes filtrar una
MUESTRA con el LLM, entrenar el prefilter con esas decisiones, y dejar que el
modelo local resuelva la mayor parte del resto — bajando muchísimo el gasto
de API. Filtrando en línea el prefilter llega tarde.

Reanudable: cursor sidecar (`<salida>.cursor`) y cortacircuitos de cuota. Si
se agotan los créditos se detiene SIN avanzar el cursor y al relanzarlo
continúa en el mismo artículo.

Uso:
    # todo el corpus
    python scripts/filter_corpus.py

    # una muestra primero, para entrenar el prefilter con sus decisiones
    python scripts/filter_corpus.py --limit 2500
    python scripts/train_prefilter.py
    python scripts/filter_corpus.py --prefilter        # el resto, ya barato

    # rutas explícitas
    python scripts/filter_corpus.py --input data/raw/articles_unfiltered.jsonl \\
        --output data/raw/articles.jsonl
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import LOGS_DIR, RAW_DIR  # noqa: E402
from src.scraper.article_filter import is_real_article  # noqa: E402
from src.scraper.prefilter import try_load_prefilter  # noqa: E402

logger = logging.getLogger("filter_corpus")

_TEXT_HEAD_CHARS = 3000
_MAX_CONSECUTIVE_FAILURES = 5


def _cursor_path(output_path: Path) -> Path:
    return Path(str(output_path) + ".cursor")


def _read_cursor(output_path: Path) -> int:
    path = _cursor_path(output_path)
    return int(path.read_text().strip()) if path.exists() else 0


def _write_cursor(output_path: Path, line_num: int) -> None:
    _cursor_path(output_path).write_text(str(line_num))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filtra un corpus ya recolectado (politicidad + colombianidad)",
    )
    parser.add_argument("--input", type=str, default=None,
                        help="JSONL sin filtrar (default: data/raw/articles_unfiltered.jsonl)")
    parser.add_argument("--output", type=str, default=None,
                        help="JSONL filtrado (default: data/raw/articles.jsonl)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Procesar solo N artículos en esta corrida "
                             "(útil para filtrar una muestra y entrenar el prefilter)")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash-lite")
    parser.add_argument("--escalate-model", type=str, default="gemini-2.5-flash")
    parser.add_argument("--no-escalate", action="store_true")
    parser.add_argument("--escalate-threshold", type=float, default=0.7)
    parser.add_argument("--rate-limit", type=float, default=4.5,
                        help="Segundos entre llamadas (4.5 = free tier)")
    parser.add_argument("--prefilter", nargs="?", const="__default__", default=None,
                        help="Usa el prefilter local para resolver gratis lo obvio")
    parser.add_argument("--force", action="store_true",
                        help="Re-filtrar desde cero (trunca la salida y el cursor)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # El SDK de Gemini y httpx loguean cada petición: ensucia la barra de tqdm.
    for noisy in ("google_genai", "google_genai.types", "httpx", "httpcore",
                  "google.genai", "google.genai.models"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    input_path = Path(args.input) if args.input else RAW_DIR / "articles_unfiltered.jsonl"
    output_path = Path(args.output) if args.output else RAW_DIR / "articles.jsonl"
    filter_log = LOGS_DIR / "filter_decisions.jsonl"

    if not input_path.exists():
        raise SystemExit(
            f"✗ No existe {input_path}\n"
            "  Recolecta primero sin filtro:\n"
            "    python scripts/collect_corpus.py --no-filter --target 49000"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_log.parent.mkdir(parents=True, exist_ok=True)

    from dotenv import load_dotenv
    from google import genai

    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("✗ Falta GEMINI_API_KEY en .env")
    client = genai.Client(api_key=api_key)

    prefilter = None
    if args.prefilter:
        path = ("data/models/prefilter.joblib" if args.prefilter == "__default__"
                else args.prefilter)
        prefilter = try_load_prefilter(path)

    if args.force:
        _write_cursor(output_path, 0)
        cursor = 0
        mode = "w"
    else:
        cursor = _read_cursor(output_path)
        mode = "a"
        if output_path.exists() and output_path.stat().st_size > 0 and cursor == 0:
            raise SystemExit(
                f"✗ {output_path} ya tiene contenido pero el cursor está en 0.\n"
                "  Appendear duplicaría artículos. Usa --force para re-filtrar."
            )

    with open(input_path, encoding="utf-8") as f:
        total_lines = sum(1 for line in f if line.strip())

    pending = total_lines - cursor
    if args.limit is not None:
        pending = min(pending, args.limit)

    print("=" * 66)
    print("  FILTRADO DEL CORPUS")
    print(f"  Entrada:    {input_path.name} ({total_lines:,} artículos)")
    print(f"  Ya filtrados: {cursor:,}")
    print(f"  En esta corrida: {pending:,}")
    print(f"  Prefilter:  {'SÍ' if prefilter else 'NO'}")
    print(f"  Modelo:     {args.model}")
    print("=" * 66)
    print()

    if pending <= 0:
        print("✓ Nada pendiente. Corpus filtrado completo.")
        return

    from tqdm import tqdm

    counts: Counter = Counter()
    processed = 0
    consecutive_failures = 0
    started = time.time()
    escalate = None if args.no_escalate else args.escalate_model

    pbar = tqdm(total=pending, desc="Filtrando", unit="art", smoothing=0.1)
    try:
        with open(input_path, encoding="utf-8") as fin, \
             open(output_path, mode, encoding="utf-8") as fout, \
             open(filter_log, "a", encoding="utf-8") as flog:

            for i, line in enumerate(fin):
                if i < cursor:
                    continue
                if args.limit is not None and processed >= args.limit:
                    break
                line = line.strip()
                if not line:
                    continue

                try:
                    article = json.loads(line)
                    text = article["text"]
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Línea %d corrupta (%s), saltando.", i + 1, exc)
                    counts["corrupta"] += 1
                    _write_cursor(output_path, i + 1)
                    processed += 1
                    pbar.update(1)
                    continue

                engine = "llm"
                info: dict | None = None
                is_political = False

                # Etapa 0: prefilter local (gratis)
                if prefilter is not None:
                    decision = prefilter.decide(text[:_TEXT_HEAD_CHARS])
                    if decision.action != "uncertain":
                        engine = "prefilter"
                        is_political = decision.action == "keep"
                        info = {
                            "category": ("political_article" if is_political
                                         else "nonpolitical_article"),
                            "confidence": round(decision.probability, 4),
                            "reason": f"prefilter p={decision.probability:.3f}",
                            "text_issues": [],
                        }

                # Etapa 1: filter LLM (zona gris o sin prefilter)
                if info is None:
                    time.sleep(args.rate_limit)
                    is_political, info = is_real_article(
                        client, text, model=args.model,
                        escalate_model=escalate,
                        escalate_threshold=args.escalate_threshold,
                    )
                    if info is None:
                        consecutive_failures += 1
                        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                            print(f"\n\n⚠ {consecutive_failures} fallos consecutivos "
                                  "del LLM (¿cuota agotada?).")
                            print(f"  El cursor queda en {i}: relanza el mismo "
                                  "comando cuando se restablezca.")
                            break
                        counts["filter_error"] += 1
                        _write_cursor(output_path, i + 1)
                        processed += 1
                        pbar.update(1)
                        continue
                    consecutive_failures = 0

                flog.write(json.dumps({
                    "id": article.get("id"),
                    "url": article.get("url"),
                    "source": article.get("source"),
                    "engine": engine,
                    "category": info.get("category"),
                    "confidence": info.get("confidence"),
                    "reason": info.get("reason"),
                    "kept": is_political,
                    "escalated": info.get("escalated", False),
                    "text_issues": info.get("text_issues", []),
                    "text_head": text[:_TEXT_HEAD_CHARS],
                }, ensure_ascii=False) + "\n")
                flog.flush()

                if is_political:
                    fout.write(json.dumps(article, ensure_ascii=False) + "\n")
                    fout.flush()
                    counts["kept" if engine == "llm" else "kept_prefilter"] += 1
                else:
                    counts[f"drop:{info.get('category', '?')}"] += 1
                for issue in info.get("text_issues", []):
                    counts[f"issue:{issue}"] += 1

                _write_cursor(output_path, i + 1)
                processed += 1
                pbar.update(1)
                pbar.set_postfix(
                    keep=counts["kept"] + counts["kept_prefilter"],
                    drop=sum(v for k, v in counts.items() if k.startswith("drop:")),
                )
    except KeyboardInterrupt:
        print("\n\n⏸  Interrumpido. El cursor quedó guardado.")
    finally:
        pbar.close()

    kept = counts["kept"] + counts["kept_prefilter"]
    dropped = sum(v for k, v in counts.items() if k.startswith("drop:"))
    print()
    print("=" * 66)
    print(f"  Procesados:  {processed:,} en {time.time() - started:.0f}s")
    print(f"  ✓ Conservados: {kept:,}"
          f" (LLM: {counts['kept']:,}, prefilter: {counts['kept_prefilter']:,})")
    print(f"  ⊘ Descartados: {dropped:,}")
    for key in sorted(k for k in counts if k.startswith("drop:")):
        print(f"      {key[5:]:24} {counts[key]:,}")
    issues = sorted(k for k in counts if k.startswith("issue:"))
    if issues:
        print("  Problemas de texto detectados:")
        for key in issues:
            print(f"      {key[6:]:24} {counts[key]:,}")
    if counts["filter_error"]:
        print(f"  ⚠ Errores del filtro: {counts['filter_error']:,} (se reintentan)")
    print(f"  Salida: {output_path}")

    remaining = total_lines - _read_cursor(output_path)
    if remaining > 0:
        print(f"\n  Faltan {remaining:,}. Continuar con el mismo comando.")
    else:
        print("\n  ✓ Corpus filtrado completo. Siguiente paso:")
        print("      python scripts/label.py     # etiquetado silver")
    print("=" * 66)


if __name__ == "__main__":
    main()
