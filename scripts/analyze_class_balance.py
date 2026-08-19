"""Analiza el balance de clases del corpus etiquetado: clase × fuente/categoría.

Responde la pregunta operativa del scraping dirigido: ¿qué fuentes producen
las clases minoritarias? Con eso se decide QUÉ scrapear más (en vez de
scrapear uniforme y esperar que el desbalance se arregle solo).

Uso:
    python scripts/analyze_class_balance.py
    python scripts/analyze_class_balance.py --input data/processed/dataset.jsonl
    python scripts/analyze_class_balance.py --by category
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Balance de clases por fuente")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL etiquetado (default: data/silver/silver_set.jsonl)",
    )
    parser.add_argument(
        "--by", choices=["source", "category"], default="source",
        help="Agrupar por fuente individual o por categoría de fuente",
    )
    parser.add_argument(
        "--min-share", type=float, default=0.05,
        help="Umbral de 'clase minoritaria': share del corpus < este valor "
             "(default: 0.05 = 5%%; equilibrado sería 12.5%% por clase)",
    )
    args = parser.parse_args()

    from src.core.paths import SILVER_DIR
    from src.core.schema import IDEOLOGY_CLASSES
    from src.training.data.dataset import resolve_label_idx

    input_path = Path(args.input) if args.input else SILVER_DIR / "silver_set.jsonl"
    if not input_path.exists():
        print(f"✗ No existe {input_path}")
        return

    class_totals: Counter = Counter()
    by_group: dict[str, Counter] = defaultdict(Counter)
    total = 0
    unresolved = 0

    with open(input_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            article = json.loads(line)
            try:
                label = IDEOLOGY_CLASSES[resolve_label_idx(article)]
            except ValueError:
                unresolved += 1
                continue
            group = article.get(args.by, "?") or "?"
            class_totals[label] += 1
            by_group[group][label] += 1
            total += 1

    if total == 0:
        print("✗ Sin artículos etiquetados resolubles.")
        return

    print()
    print("=" * 76)
    print(f"  BALANCE DE CLASES — {input_path.name} ({total} artículos"
          + (f", {unresolved} sin etiqueta)" if unresolved else ")"))
    print("=" * 76)
    print(f"\n  {'Clase':<18} {'n':>5} {'share':>7}   (equilibrado = 12.5%)")
    for cls in IDEOLOGY_CLASSES:
        n = class_totals.get(cls, 0)
        share = n / total
        flag = "  ⚠ MINORITARIA" if share < args.min_share else ""
        print(f"  {cls:<18} {n:>5} {share:>6.1%}{flag}")

    minority = [
        cls for cls in IDEOLOGY_CLASSES
        if class_totals.get(cls, 0) / total < args.min_share
    ]
    if minority:
        print(f"\n  Mejores {args.by}s para cada clase minoritaria "
              "(scraping dirigido):")
        for cls in minority:
            producers = sorted(
                ((group, counts[cls]) for group, counts in by_group.items()
                 if counts[cls] > 0),
                key=lambda pair: -pair[1],
            )[:5]
            if producers:
                detail = ", ".join(f"{g} ({n})" for g, n in producers)
            else:
                detail = "NINGUNA fuente la produce — buscar fuentes nuevas"
            print(f"    {cls:<18} → {detail}")
        print(f"\n  Sugerencia: python scripts/scraper.py --{args.by.replace('source', 'sources')} "
              "<las de arriba> --max-articles 100")
    print()


if __name__ == "__main__":
    main()
