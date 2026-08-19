"""Audita (y opcionalmente repara) la calidad de un corpus YA scrapeado.

Aplica el cleaner ACTUAL y la compuerta de calidad a cada artículo de un
JSONL existente. Sirve para dos cosas:

1. **Auditar**: medir cuánto boilerplate residual y cuántos no-artículos
   (páginas de listado, prosa rota) hay en el corpus.
2. **Reparar** (`--fix`): escribir un corpus nuevo con los textos re-limpiados
   y SIN los artículos que fallan la compuerta (sus ids quedan en un reporte).

Típico antes de re-etiquetar el silver:
    python scripts/audit_corpus_quality.py --input data/raw/articles.jsonl
    python scripts/audit_corpus_quality.py --input data/raw/articles.jsonl \\
        --fix --output data/raw/articles_clean.jsonl
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src.scraper.cleaner import clean_article_text
from src.scraper.quality import assess_article_quality

MIN_CHARS_DEFAULT = 800


def main() -> None:
    parser = argparse.ArgumentParser(description="Auditoría/reparación de calidad del corpus")
    parser.add_argument("--input", required=True, help="JSONL a auditar")
    parser.add_argument(
        "--fix", action="store_true",
        help="Escribe el corpus reparado (re-limpiado + sin artículos de baja calidad)",
    )
    parser.add_argument("--output", type=str, default=None, help="JSONL de salida (con --fix)")
    parser.add_argument("--min-chars", type=int, default=MIN_CHARS_DEFAULT)
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"✗ No existe {input_path}")
        return

    articles = [json.loads(line) for line in open(input_path, encoding="utf-8") if line.strip()]

    kept: list[dict] = []
    dropped: list[dict] = []
    reasons: Counter = Counter()
    chars_removed = 0

    for article in articles:
        original = article["text"]
        cleaned = clean_article_text(
            original,
            source_name=article.get("source"),
            authors=article.get("authors"),
        )
        chars_removed += max(0, len(original) - len(cleaned))
        article = {**article, "text": cleaned}

        if len(cleaned) < args.min_chars:
            reasons["muy_corto_post_limpieza"] += 1
            dropped.append({**article, "_drop_reason": "muy_corto_post_limpieza"})
            continue

        verdict = assess_article_quality(article.get("title", ""), cleaned)
        if not verdict.ok:
            reason = verdict.reasons[0]
            reasons[reason] += 1
            dropped.append({**article, "_drop_reason": reason, "_metrics": verdict.metrics})
            continue

        kept.append(article)

    print()
    print("=" * 64)
    print(f"  AUDITORÍA DE CALIDAD — {input_path.name}")
    print(f"  Artículos:            {len(articles)}")
    print(f"  ✓ Pasan la compuerta: {len(kept)}")
    print(f"  ⊘ Rechazados:         {len(dropped)}")
    for reason, count in reasons.most_common():
        print(f"      {reason:28} {count}")
    print(f"  Basura removida:      {chars_removed:,} caracteres "
          f"({chars_removed / max(1, sum(len(a['text']) for a in articles)):.1%} del corpus)")
    print("=" * 64)

    if dropped:
        print("\n  Rechazados (id · fuente · título):")
        for record in dropped[:15]:
            print(f"    {record.get('id', '?')} · {record.get('source', '?'):16} · "
                  f"[{record['_drop_reason']}] {record.get('title', '')[:55]}")
        if len(dropped) > 15:
            print(f"    … y {len(dropped) - 15} más")

    if args.fix:
        output_path = (
            Path(args.output) if args.output
            else input_path.with_name(input_path.stem + "_clean.jsonl")
        )
        with open(output_path, "w", encoding="utf-8") as f:
            for article in kept:
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
        dropped_path = output_path.with_name(output_path.stem + "_rechazados.jsonl")
        with open(dropped_path, "w", encoding="utf-8") as f:
            for record in dropped:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"\n✓ Corpus reparado: {output_path} ({len(kept)} artículos)")
        print(f"✓ Rechazados:      {dropped_path} (revisables)")
        print("\nSiguiente paso: re-etiquetar con "
              f"`python scripts/label.py --input {output_path} --force`")


if __name__ == "__main__":
    main()
