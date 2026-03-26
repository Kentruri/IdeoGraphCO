"""Scraper de noticias colombianas usando Newspaper4k.

Uso:
    python scripts/scraper.py
    python scripts/scraper.py --categories nacional independiente --max-articles 100
    python scripts/scraper.py --use-rss --max-articles 200
    python scripts/scraper.py --categories institucional --max-articles 30
    python scripts/scraper.py --sources eltiempo lasillavacia --max-articles 50
"""

import argparse
import json
import logging
from collections import Counter

from src.data.scraping import get_newspaper_config, scrape_rss, scrape_source
from src.data.sources import (
    ALL_SOURCES,
    CATEGORIES,
    RSS_FEEDS,
    SOURCE_CATEGORY,
    SOURCES_CONFIG,
)
from src.paths import RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def resolve_sources(categories: list[str] | None, sources: list[str] | None) -> list[str]:
    """Resuelve qué fuentes scrapear según categorías y/o nombres individuales."""
    if sources:
        return sources
    if categories:
        names: list[str] = []
        for cat in categories:
            if cat in SOURCES_CONFIG:
                names.extend(SOURCES_CONFIG[cat].keys())
            else:
                logger.warning("Categoría '%s' no reconocida, saltando.", cat)
        return names
    return list(ALL_SOURCES.keys())


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper de noticias colombianas")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=CATEGORIES,
        default=None,
        help="Categorías a scrapear: nacional, independiente, institucional, regional, gremial",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        help="Fuentes individuales (ej: eltiempo semana lasillavacia)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=50,
        help="Máximo de artículos por fuente (default: 50)",
    )
    parser.add_argument(
        "--use-rss",
        action="store_true",
        help="Usar feeds RSS cuando estén disponibles (más limpio)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Archivo de salida (default: data/raw/news.jsonl)",
    )
    args = parser.parse_args()

    output_path = RAW_DIR / (args.output or "news.jsonl")
    config = get_newspaper_config()
    all_articles: list[dict] = []
    source_names = resolve_sources(args.categories, args.sources)

    for name in source_names:
        url = ALL_SOURCES.get(name)
        category = SOURCE_CATEGORY.get(name, "desconocido")

        if url is None:
            logger.warning("Fuente '%s' no reconocida, saltando.", name)
            continue

        if args.use_rss and name in RSS_FEEDS:
            articles = scrape_rss(name, RSS_FEEDS[name], category, args.max_articles, config)
        else:
            articles = scrape_source(name, url, category, args.max_articles, config)

        all_articles.extend(articles)

    # Guardar como JSONL
    with open(output_path, "w", encoding="utf-8") as f:
        for article in all_articles:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")

    # Resumen por categoría
    cat_counts = Counter(a["category"] for a in all_articles)
    logger.info("Total: %d artículos guardados en %s", len(all_articles), output_path)
    for cat, count in cat_counts.most_common():
        logger.info("  [%s]: %d artículos", cat, count)


if __name__ == "__main__":
    main()
