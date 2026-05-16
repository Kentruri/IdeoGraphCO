"""Scraper de noticias políticas colombianas con Trafilatura.

Extrae únicamente noticias de secciones políticas usando:
- RSS feeds de secciones políticas
- Sitemaps filtrados por URL
- Crawl directo para medios 100% políticos

Uso:
    python scripts/scraper.py
    python scripts/scraper.py --categories nacional independiente --max-articles 100
    python scripts/scraper.py --sources eltiempo lasillavacia --max-articles 50
"""

import argparse
import json
import logging
from collections import Counter

from tqdm import tqdm

from src.data.scraping import get_scraped_count, scrape_source
from src.data.sources import CATEGORIES, SOURCES, SOURCES_BY_CATEGORY
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
            if cat in SOURCES_BY_CATEGORY:
                names.extend(SOURCES_BY_CATEGORY[cat])
            else:
                logger.warning("Categoría '%s' no reconocida, saltando.", cat)
        return names
    return list(SOURCES.keys())


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper de noticias políticas colombianas")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=CATEGORIES,
        default=None,
        help="Categorías a scrapear",
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=None,
        help="Fuentes individuales (ej: eltiempo lasillavacia)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=50,
        help="Máximo de artículos por fuente (default: 50)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Archivo de salida (default: data/raw/news.jsonl)",
    )
    args = parser.parse_args()

    output_path = RAW_DIR / (args.output or "news.jsonl")
    source_names = resolve_sources(args.categories, args.sources)
    total_sources = len(source_names)
    total_articles = 0

    print()
    print("=" * 60)
    print("  IdeoGraphCO Scraper (Trafilatura)")
    print(f"  Fuentes: {total_sources} | Máx por fuente: {args.max_articles}")
    print(f"  Salida: {output_path}")
    print(f"  BD histórica: {get_scraped_count()} artículos previos")
    print("=" * 60)
    print()

    # Barra de progreso general
    source_pbar = tqdm(
        source_names,
        desc="Progreso total",
        unit="fuente",
        position=0,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} fuentes [{elapsed}<{remaining}] {postfix}",
    )

    with open(output_path, "a", encoding="utf-8") as f:
        for name in source_pbar:
            if name not in SOURCES:
                logger.warning("Fuente '%s' no reconocida, saltando.", name)
                continue

            source_config = SOURCES[name]
            source_pbar.set_postfix_str(
                f"{name} [{source_config['category']}] | {total_articles} artículos totales"
            )

            logger.info("[%s] mode=%s", name, source_config["mode"])
            articles = scrape_source(name, source_config, args.max_articles)

            for article in articles:
                f.write(json.dumps(article, ensure_ascii=False) + "\n")
                f.flush()

            total_articles += len(articles)

    source_pbar.close()

    # Resumen final
    print()
    print("=" * 60)
    print("  SCRAPING COMPLETADO")
    print(f"  Artículos nuevos: {total_articles}")
    print(f"  Total en BD: {get_scraped_count()}")
    print(f"  Guardados en: {output_path}")

    try:
        cat_counts: Counter[str] = Counter()
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                article = json.loads(line)
                cat_counts[article["category"]] += 1
        print("-" * 40)
        print("  Desglose por categoría:")
        for cat, count in cat_counts.most_common():
            print(f"    [{cat}]: {count} artículos")
    except Exception:
        pass

    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
