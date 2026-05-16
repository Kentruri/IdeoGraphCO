"""Filtra artículos basura del dataset etiquetado y limpia prefijos.

Pipeline:
1. Para cada artículo en data/interim/labeled_news.jsonl:
   a) Aplica cleaner mejorado al texto (remueve cookie banner remnants, etc.)
   b) Pregunta al LLM si es un artículo real o basura
   c) Si es basura → descartar
   d) Si es real → guardar con texto limpio
2. Salida: data/interim/labeled_news_clean.jsonl

Requiere GEMINI_API_KEY en .env

Uso:
    python scripts/filter_articles.py
    python scripts/filter_articles.py --max-articles 10   # prueba
    python scripts/filter_articles.py --force              # re-filtrar todo
    python scripts/filter_articles.py --dry-run            # solo reporta
"""

import argparse
import json
import logging
import os
import time
from collections import Counter
from pathlib import Path

# Cargar variables de .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


CURSOR_NAME = ".filter_cursor"


def read_cursor(path: Path) -> int:
    """Lee la última línea filtrada (0 si no hay cursor)."""
    if path.exists():
        return int(path.read_text().strip())
    return 0


def write_cursor(path: Path, line_num: int) -> None:
    """Guarda la última línea filtrada."""
    path.write_text(str(line_num))


def main() -> None:
    parser = argparse.ArgumentParser(description="Filtra artículos basura del dataset")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL etiquetado (default: data/interim/labeled_news.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="JSONL filtrado (default: data/interim/labeled_news_clean.jsonl)",
    )
    parser.add_argument(
        "--max-articles", type=int, default=None,
        help="Límite de artículos a filtrar (None = todos)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-filtrar todo desde cero (ignora cursor)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Solo reporta resultados, no escribe archivo",
    )
    parser.add_argument(
        "--model", type=str, default="gemini-2.5-flash-lite",
        help="Modelo de Gemini (default: gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--rate-limit", type=float, default=1.5,
        help="Segundos entre requests (default: 1.5s = ~40 RPM)",
    )
    args = parser.parse_args()

    # Verificar API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error(
            "Falta GEMINI_API_KEY. Configura en .env:\n"
            "  GEMINI_API_KEY=AIzaSy..."
        )
        return

    # Importar dependencias
    try:
        from google import genai
    except ImportError:
        logger.error("Instala el SDK: pip install google-genai")
        return

    from src.data.scraping.cleaner import clean_article_text
    from src.labeling.article_filter import is_real_article
    from src.paths import INTERIM_DIR

    # Rutas
    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news.jsonl"
    output_path = Path(args.output) if args.output else INTERIM_DIR / "labeled_news_clean.jsonl"
    cursor_path = INTERIM_DIR / CURSOR_NAME

    if not input_path.exists():
        logger.error("No existe %s. Corre el etiquetado primero.", input_path)
        return

    # Cliente Gemini
    client = genai.Client(api_key=api_key)

    # Cursor
    cursor = 0 if (args.force or args.dry_run) else read_cursor(cursor_path)
    mode = "w" if args.force else "a"

    # Contar total
    with open(input_path, encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)

    pending = total_lines - cursor
    if args.max_articles is not None:
        pending = min(pending, args.max_articles)

    if pending <= 0:
        logger.info("Todo filtrado. %d artículos procesados, 0 pendientes.", cursor)
        return

    print()
    print("=" * 60)
    print("  IdeoGraphCO — Filtro de artículos basura")
    print(f"  Modelo: {args.model}")
    print(f"  Total entrada: {total_lines}")
    print(f"  Ya filtrados: {cursor}")
    print(f"  Pendientes: {pending}")
    print(f"  Modo: {'dry-run' if args.dry_run else ('forzado' if args.force else 'incremental')}")
    print("=" * 60)
    print()

    # Stats
    kept = 0
    discarded = 0
    error_count = 0
    categories: Counter[str] = Counter()
    discarded_examples: list[tuple[str, str, str]] = []

    fout = None
    if not args.dry_run:
        fout = open(output_path, mode, encoding="utf-8")

    try:
        with open(input_path, encoding="utf-8") as fin:
            for i, line in enumerate(fin):
                if i < cursor:
                    continue

                if args.max_articles is not None and (kept + discarded) >= args.max_articles:
                    break

                line = line.strip()
                if not line:
                    continue

                article = json.loads(line)

                # 1. Limpiar el texto con regex
                cleaned_text = clean_article_text(
                    article["text"],
                    authors=article.get("authors"),
                )

                # Si quedó muy corto post-limpieza, descartar sin LLM
                if len(cleaned_text) < 300:
                    discarded += 1
                    categories["too_short_after_clean"] += 1
                    if len(discarded_examples) < 15:
                        discarded_examples.append(
                            (article.get("url", ""), "too_short", "")
                        )
                    if not args.dry_run:
                        write_cursor(cursor_path, i + 1)
                    continue

                # 2. Preguntar al LLM si es artículo real
                is_article, info = is_real_article(client, cleaned_text, args.model)

                if info is None:
                    error_count += 1
                    if not args.dry_run:
                        write_cursor(cursor_path, i + 1)
                    continue

                category = info.get("category", "unknown")
                categories[category] += 1

                if is_article:
                    # 3. Conservar con texto limpio
                    article["text"] = cleaned_text
                    if not args.dry_run and fout:
                        fout.write(json.dumps(article, ensure_ascii=False) + "\n")
                        fout.flush()
                    kept += 1
                else:
                    discarded += 1
                    if len(discarded_examples) < 15:
                        discarded_examples.append((
                            article.get("url", ""),
                            category,
                            info.get("reason", "")[:100],
                        ))

                if not args.dry_run:
                    write_cursor(cursor_path, i + 1)

                if (kept + discarded) % 25 == 0:
                    logger.info(
                        "  Procesados: %d/%d | Conservados: %d | Descartados: %d",
                        kept + discarded, pending, kept, discarded,
                    )

                # Rate limit
                time.sleep(args.rate_limit)
    finally:
        if fout:
            fout.close()

    # Resumen
    print()
    print("=" * 60)
    print("  RESULTADO DEL FILTRADO")
    print(f"  Total procesados: {kept + discarded}")
    print(f"  ✓ Conservados (artículos reales): {kept}")
    print(f"  ✗ Descartados (basura): {discarded}")
    print(f"  ! Errores LLM: {error_count}")
    print()
    print("  Distribución de categorías:")
    for cat, count in categories.most_common():
        print(f"    {cat}: {count}")
    print()
    print("  Ejemplos descartados:")
    for url, cat, reason in discarded_examples:
        print(f"    [{cat}] {url[:80]}")
        if reason:
            print(f"      → {reason}")
    if not args.dry_run:
        print(f"\n  Salida: {output_path}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
