"""Extrae los textos limpios de labeled_news_clean.jsonl para re-etiquetar.

Después de correr filter_articles.py, los artículos sobrevivientes quedan en
data/interim/labeled_news_clean.jsonl con labels viejos (escala 0-100). Este
script descarta los labels y produce un archivo solo-textos listo para
re-etiquetar con la nueva escala 1-5 vía scripts/label.py.

Uso:
    python scripts/extract_clean_texts.py
    python scripts/extract_clean_texts.py --output data/raw/news_filtered.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Campos del raw que conservamos (todo lo demás es label viejo y se descarta)
META_FIELDS: tuple[str, ...] = ("text", "title", "source", "category", "url", "date")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrae textos limpios de labeled_news_clean.jsonl"
    )
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL filtrado (default: data/interim/labeled_news_clean.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="JSONL solo-textos (default: data/raw/news_filtered.jsonl)",
    )
    args = parser.parse_args()

    from src.paths import INTERIM_DIR, RAW_DIR

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news_clean.jsonl"
    output_path = Path(args.output) if args.output else RAW_DIR / "news_filtered.jsonl"

    if not input_path.exists():
        logger.error("No existe %s. Corre primero scripts/filter_articles.py.", input_path)
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    n_in = 0
    n_out = 0
    with open(input_path, encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            n_in += 1
            article = json.loads(line)
            stripped = {k: article[k] for k in META_FIELDS if k in article}
            fout.write(json.dumps(stripped, ensure_ascii=False) + "\n")
            n_out += 1

    print()
    print("=" * 60)
    print("  Extracción de textos limpios")
    print(f"  Entrada: {input_path} ({n_in} artículos)")
    print(f"  Salida:  {output_path} ({n_out} artículos)")
    print()
    print("  Siguiente paso (re-etiquetar con escala 1-5):")
    print("    rm data/interim/.label_cursor data/interim/labeled_news.jsonl")
    print(f"    python scripts/label.py --input {output_path} --force")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
