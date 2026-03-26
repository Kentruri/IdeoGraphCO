"""Funciones de descarga, parseo y enriquecimiento de artículos."""

import logging
import random
import time
from datetime import datetime, timezone

import feedparser
from newspaper import Article, Config, build

logger = logging.getLogger(__name__)


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
        # Rate limiting: respiro entre descargas para evitar baneo de IP
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
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            data = parse_article(url, name, category, config)
            if data:
                articles.append(data)
            time.sleep(random.uniform(0.5, 1.5))

    logger.info("  → %d artículos obtenidos de %s (RSS)", len(articles), name)
    return articles
