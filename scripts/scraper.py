"""Scraper de noticias colombianas usando Newspaper4k.

Fuentes categorizadas por tipo para garantizar balance en las 8 dimensiones
ideológicas del modelo IdeoVect.

Uso:
    python scripts/scraper.py
    python scripts/scraper.py --categories nacional independiente --max-articles 100
    python scripts/scraper.py --use-rss --max-articles 200
    python scripts/scraper.py --categories institucional --max-articles 30
"""

import argparse
import json
import logging
import random
import time
from datetime import datetime, timezone

import feedparser
from newspaper import Article, Config, build

from src.paths import RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fuentes categorizadas por tipo de medio y dimensión ideológica que potencian
# ---------------------------------------------------------------------------

SOURCES_CONFIG: dict[str, dict[str, str]] = {
    # --- Nacionales tradicionales (línea base ideológica) ---
    "nacional": {
        "eltiempo": "https://www.eltiempo.com",
        "elespectador": "https://www.elespectador.com",
        "semana": "https://www.semana.com",
        "elnuevosiglo": "https://www.elnuevosiglo.com.co",
        "portafolio": "https://www.portafolio.co",
        "bluradio": "https://www.bluradio.com",
        "rcnradio": "https://www.rcnradio.com",
        "caracol": "https://www.caracol.com.co",
    },
    # --- Independientes e investigativos (populismo, doctrinarismo, progresismo) ---
    "independiente": {
        "lasillavacia": "https://www.lasillavacia.com",
        "cambio": "https://cambiocolombia.com",
        "cuestionpublica": "https://cuestionpublica.com",
        "voragine": "https://voragine.co",
        "lanuevaprensa": "https://www.lanuevaprensa.com.co",
        "mutante": "https://www.mutante.org",
        "razonpublica": "https://razonpublica.com",
    },
    # --- Institucionales (institucionalismo puro) ---
    "institucional": {
        "presidencia": "https://www.presidencia.gov.co/prensa/noticias",
        "vicepresidencia": "https://www.vicepresidencia.gov.co/prensa/noticias",
        "funcionpublica": "https://www.funcionpublica.gov.co/todas-las-noticias",
        "senado": "https://www.senado.gov.co/index.php/noticias",
    },
    # --- Regionales (personalismo local, soberanismo) ---
    "regional": {
        "elcolombiano": "https://www.elcolombiano.com",
        "elheraldo": "https://www.elheraldo.co",
        "eluniversal": "https://www.eluniversal.com.co",
        "vanguardia": "https://www.vanguardia.com",
        "laopinion": "https://www.laopinion.com.co",
        "elpaiscali": "https://www.elpais.com.co",
    },
    # --- Gremiales y especializadas (soberanismo vs. globalismo) ---
    "gremial": {
        "fecode": "https://fecode.edu.co",
        "andi": "https://www.andi.com.co",
    },
}

# Vista plana: nombre → url (se construye automáticamente)
ALL_SOURCES: dict[str, str] = {}
for _sources in SOURCES_CONFIG.values():
    ALL_SOURCES.update(_sources)

# Mapeo inverso: nombre → categoría
SOURCE_CATEGORY: dict[str, str] = {}
for _cat, _sources in SOURCES_CONFIG.items():
    for _name in _sources:
        SOURCE_CATEGORY[_name] = _cat

# ---------------------------------------------------------------------------
# Feeds RSS conocidos (más limpios que build() para noticias políticas)
# ---------------------------------------------------------------------------

RSS_FEEDS: dict[str, list[str]] = {
    "eltiempo": [
        "https://www.eltiempo.com/rss/colombia.xml",
        "https://www.eltiempo.com/rss/politica.xml",
    ],
    "elespectador": [
        "https://www.elespectador.com/rss/politica/feed/",
        "https://www.elespectador.com/rss/colombia/feed/",
    ],
    "semana": [
        "https://www.semana.com/rss/politica.xml",
    ],
}


def get_newspaper_config() -> Config:
    """Configura Newspaper4k con User-Agent real para evitar bloqueos 403."""
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    config.request_timeout = 15
    config.language = "es"
    config.memoize_articles = True
    return config


def parse_article(url: str, source: str, category: str, config: Config) -> dict | None:
    """Descarga, parsea y enriquece un artículo individual."""
    try:
        article = Article(url, config=config)
        article.download()
        article.parse()

        if not article.text or len(article.text) < 200:
            return None

        # NLP de Newspaper: genera keywords y resumen automático
        article.nlp()

        return {
            "text": article.text,
            "title": article.title,
            "summary": article.summary,
            "keywords": article.keywords,
            "authors": article.authors,
            "source": source,
            "category": category,
            "url": url,
            "date": article.publish_date.isoformat() if article.publish_date else None,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception:
        logger.warning("Error descargando %s", url)
        return None


def scrape_source(
    name: str, url: str, category: str, max_articles: int, config: Config,
) -> list[dict]:
    """Descarga artículos de una fuente vía build() (página principal)."""
    logger.info("Scraping %s [%s] (%s) — máx %d", name, category, url, max_articles)
    articles: list[dict] = []

    try:
        paper = build(url, config=config)
    except Exception:
        logger.exception("Error construyendo fuente %s", name)
        return articles

    for article_ref in paper.articles[:max_articles]:
        data = parse_article(article_ref.url, name, category, config)
        if data:
            articles.append(data)
        time.sleep(random.uniform(0.5, 1.5))

    logger.info("  → %d artículos obtenidos de %s", len(articles), name)
    return articles


def scrape_rss(
    name: str, feeds: list[str], category: str, max_articles: int, config: Config,
) -> list[dict]:
    """Descarga artículos desde feeds RSS (más limpio que build())."""
    logger.info("Scraping RSS de %s [%s] — máx %d", name, category, max_articles)
    articles: list[dict] = []
    seen_urls: set[str] = set()

    for feed_url in feeds:
        if len(articles) >= max_articles:
            break

        try:
            feed = feedparser.parse(feed_url)
        except Exception:
            logger.warning("Error parseando RSS %s", feed_url)
            continue

        for entry in feed.entries:
            if len(articles) >= max_articles:
                break

            url = entry.get("link", "")
            if not url or url in s∏een_urls:
                continue
            seen_urls.add(url)

            data = parse_article(url, name, category, config)
            if data:
                articles.append(data)
            time.sleep(random.uniform(0.5, 1.5))

    logger.info("  → %d artículos obtenidos de %s (RSS)", len(articles), name)
    return articles


def resolve_sources(categories: list[str] | None, sources: list[str] | None) -> list[str]:
    """Resuelve qué fuentes scrapear según categorías y/o nombres individuales."""
    names: list[str] = []

    if sources:
        # Si se especifican fuentes individuales, usar directamente
        names = sources
    elif categories:
        # Si se especifican categorías, expandir a todas sus fuentes
        for cat in categories:
            if cat in SOURCES_CONFIG:
                names.extend(SOURCES_CONFIG[cat].keys())
            else:
                logger.warning("Categoría '%s' no reconocida, saltando.", cat)
    else:
        # Por defecto: todas las fuentes
        names = list(ALL_SOURCES.keys())

    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Scraper de noticias colombianas")
    parser.add_argument(
        "--categories",
        nargs="+",
        choices=list(SOURCES_CONFIG.keys()),
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

        # RSS si está disponible y se pidió
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
    from collections import Counter
    cat_counts = Counter(a["category"] for a in all_articles)
    logger.info("Total: %d artículos guardados en %s", len(all_articles), output_path)
    for cat, count in cat_counts.most_common():
        logger.info("  [%s]: %d artículos", cat, count)


if __name__ == "__main__":
    main()
