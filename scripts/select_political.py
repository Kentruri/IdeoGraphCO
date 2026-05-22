"""Filtra los artículos políticos del JSONL etiquetado.

Aprovecha el campo `is_political` ya marcado por el LLM (escala vieja 0-100) para
descartar gratis los artículos no-políticos (accidentes, farándula, deportes,
columnas literarias) ANTES de gastar API re-filtrando basura y re-etiquetando.

Uso:
    python scripts/select_political.py
    python scripts/select_political.py --input data/interim/labeled_news.jsonl
"""

import argparse
import json
import logging
from collections import Counter
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filtra artículos políticos (is_political=1)")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL etiquetado (default: data/interim/labeled_news.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="JSONL filtrado (default: data/interim/labeled_news_political.jsonl)",
    )
    args = parser.parse_args()

    from src.core.paths import INTERIM_DIR

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news.jsonl"
    output_path = Path(args.output) if args.output else INTERIM_DIR / "labeled_news_political.jsonl"

    if not input_path.exists():
        logger.error("No existe %s.", input_path)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_total = 0
    n_political = 0
    n_nonpolitical = 0
    sources_kept: Counter[str] = Counter()
    sources_discarded: Counter[str] = Counter()

    with open(input_path, encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_total += 1
            article = json.loads(line)

            if int(article.get("is_political", 0)) == 1:
                fout.write(json.dumps(article, ensure_ascii=False) + "\n")
                n_political += 1
                sources_kept[article.get("source", "?")] += 1
            else:
                n_nonpolitical += 1
                sources_discarded[article.get("source", "?")] += 1

    print()
    print("=" * 60)
    print("  Selección de artículos políticos")
    print(f"  Entrada: {input_path}")
    print(f"  Total:        {n_total}")
    print(f"  ✓ Políticos:  {n_political} (conservados)")
    print(f"  ✗ No-políticos: {n_nonpolitical} (descartados)")
    print()
    print(f"  Top fuentes conservadas:")
    for src, c in sources_kept.most_common(5):
        print(f"    {src}: {c}")
    print()
    print(f"  Top fuentes con más descartes (no-políticos):")
    for src, c in sources_discarded.most_common(5):
        print(f"    {src}: {c}")
    print()
    print(f"  Salida: {output_path}")
    print()
    print(f"  Siguiente paso:")
    print(f"    python scripts/filter_articles.py \\")
    print(f"        --input {output_path} \\")
    print(f"        --output data/interim/labeled_news_clean.jsonl")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
