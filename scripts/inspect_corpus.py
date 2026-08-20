"""Explora el corpus mientras se recolecta: resumen, listado y lectura.

Los artículos viven SOLO en el JSONL (`data/raw/…`). La base de datos
`data/scraper_history.db` no guarda texto: únicamente URL, hash de contenido,
fuente y fecha, para no re-descargar lo mismo.

Se puede correr mientras el colector trabaja: solo lee.

Uso:
    python scripts/inspect_corpus.py                     # resumen general
    python scripts/inspect_corpus.py --tail 20           # últimos 20 títulos
    python scripts/inspect_corpus.py --source eltiempo   # solo de una fuente
    python scripts/inspect_corpus.py --search reforma    # buscar en el título
    python scripts/inspect_corpus.py --show 3            # leer el artículo #3
    python scripts/inspect_corpus.py --show a1b2c3d4     # leer por id
    python scripts/inspect_corpus.py --filtered          # el corpus YA filtrado
    python scripts/inspect_corpus.py --export corpus.csv # para abrir en Excel
"""

import argparse
import csv
import json
import statistics
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import RAW_DIR  # noqa: E402


def load(path: Path, limit: int | None = None) -> list[dict]:
    articles = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                articles.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if limit and len(articles) >= limit:
                break
    return articles


def _fold(value: str) -> str:
    """Minúsculas sin acentos, para que 'reforma' encuentre 'Reforma'."""
    nfkd = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def show_summary(articles: list[dict], path: Path) -> None:
    if not articles:
        print(f"  (vacío: {path})")
        return

    chars = sorted(len(a.get("text", "")) for a in articles)
    print(f"=== {path.name}: {len(articles):,} artículos ===\n")

    print("Longitud (caracteres)")
    print(f"  mediana {statistics.median(chars):>8,.0f}"
          f"   p90 {chars[int(0.9 * len(chars)) - 1]:>8,}"
          f"   max {chars[-1]:>8,}")
    total_chars = sum(chars)
    print(f"  total   {total_chars:>8,} chars  (~{total_chars // 4760:,} k tokens estimados)")

    print("\nPor categoría")
    for cat, n in Counter(a.get("category", "?") for a in articles).most_common():
        bar = "█" * max(1, round(30 * n / len(articles)))
        print(f"  {cat:16} {n:6,}  {bar}")

    print("\nTop 12 fuentes")
    by_source = Counter(a.get("source", "?") for a in articles)
    for src, n in by_source.most_common(12):
        pct = 100 * n / len(articles)
        flag = "  ← concentrada" if pct > 3 else ""
        print(f"  {src:24} {n:6,}  {pct:5.1f}%{flag}")
    print(f"  ({len(by_source)} fuentes distintas con al menos 1 artículo)")

    print("\nPor año de publicación")
    years = Counter((a.get("date") or "sin-fecha")[:4] for a in articles)
    for year, n in sorted(years.items()):
        bar = "█" * max(1, round(30 * n / len(articles)))
        print(f"  {year:10} {n:6,}  {bar}")


def show_list(articles: list[dict], count: int) -> None:
    subset = articles[-count:] if count > 0 else articles
    print(f"=== {len(subset)} de {len(articles):,} artículos ===\n")
    start = len(articles) - len(subset)
    for offset, article in enumerate(subset):
        idx = start + offset
        date = (article.get("date") or "?")[:10]
        print(f"  [{idx:>6}] {article.get('source', '?'):18} {date:11} "
              f"{len(article.get('text', '')):>6}c  {article.get('title', '')[:58]}")


def show_one(articles: list[dict], key: str) -> None:
    article = None
    if key.isdigit() and int(key) < len(articles):
        article = articles[int(key)]
    else:
        article = next(
            (a for a in articles if str(a.get("id", "")).startswith(key)), None,
        )
    if article is None:
        print(f"✗ No encontré '{key}'. Usa un índice (0-{len(articles) - 1}) o un id.")
        return

    print("=" * 74)
    print(f"  {article.get('title', '(sin título)')}")
    print("=" * 74)
    for field in ("id", "source", "category", "date", "url"):
        if article.get(field):
            print(f"  {field:10} {article[field]}")
    if article.get("label"):
        print(f"  {'label':10} {article['label']}  ({article.get('label_source', '?')})")
    text = article.get("text", "")
    print(f"  {'longitud':10} {len(text):,} chars\n")
    print("-" * 74)
    print(text)
    print("-" * 74)


# Excel corta las celdas a 32.767 chars; se recorta con aviso explícito para
# que nadie confunda un texto truncado con el artículo completo.
_EXCEL_CELL_LIMIT = 32000


def export_csv(articles: list[dict], path: Path) -> None:
    """Exporta a CSV para abrir en Excel o Sheets.

    El JSONL sigue siendo el formato del pipeline: este CSV es SOLO para
    mirar. El texto se recorta al límite de celda de Excel.
    """
    columns = ["id", "source", "category", "date", "title", "text", "url"]
    truncated = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for article in articles:
            row = {col: article.get(col, "") for col in columns}
            text = row["text"] or ""
            if len(text) > _EXCEL_CELL_LIMIT:
                row["text"] = text[:_EXCEL_CELL_LIMIT] + "  […TRUNCADO PARA EXCEL…]"
                truncated += 1
            writer.writerow(row)
    print(f"✓ {len(articles):,} artículos → {path}")
    print("  (utf-8-sig: Excel respeta los acentos al abrirlo)")
    if truncated:
        print(f"  ⚠ {truncated} textos recortados al límite de celda de Excel.")
        print("    El texto íntegro sigue en el JSONL — el CSV es solo para mirar.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Explora el corpus recolectado")
    parser.add_argument("--input", type=str, default=None,
                        help="JSONL a leer (default: el sin filtrar, si existe)")
    parser.add_argument("--filtered", action="store_true",
                        help="Leer data/raw/articles.jsonl (el ya filtrado)")
    parser.add_argument("--tail", type=int, default=0,
                        help="Listar los últimos N títulos")
    parser.add_argument("--source", type=str, default=None,
                        help="Solo artículos de esta fuente")
    parser.add_argument("--category", type=str, default=None)
    parser.add_argument("--search", type=str, default=None,
                        help="Buscar texto en el título (sin distinguir acentos)")
    parser.add_argument("--show", type=str, default=None,
                        help="Imprimir un artículo completo (índice o id)")
    parser.add_argument("--export", type=str, default=None,
                        help="Exportar a CSV (para Excel/Sheets). Respeta los "
                             "filtros --source/--category/--search")
    args = parser.parse_args()

    if args.input:
        path = Path(args.input)
    elif args.filtered:
        path = RAW_DIR / "articles.jsonl"
    else:
        unfiltered = RAW_DIR / "articles_unfiltered.jsonl"
        path = unfiltered if unfiltered.exists() else RAW_DIR / "articles.jsonl"

    if not path.exists():
        raise SystemExit(
            f"✗ No existe {path}\n"
            "  Arranca la recolección:  ./scripts/collector.sh start"
        )

    articles = load(path)

    if args.source:
        articles = [a for a in articles if a.get("source") == args.source]
    if args.category:
        articles = [a for a in articles if a.get("category") == args.category]
    if args.search:
        needle = _fold(args.search)
        articles = [a for a in articles if needle in _fold(a.get("title", ""))]

    if args.export:
        export_csv(articles, Path(args.export))
    elif args.show is not None:
        show_one(articles, args.show)
    elif args.tail or args.search or args.source or args.category:
        show_list(articles, args.tail or len(articles))
    else:
        show_summary(articles, path)


if __name__ == "__main__":
    main()
