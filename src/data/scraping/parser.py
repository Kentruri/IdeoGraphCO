"""Extracción de artículos políticos colombianos con Trafilatura.

Flujo por fuente:
1. RSS feeds (si disponibles) → URLs limpias de secciones políticas
2. Sitemap + filtro de URL → URLs históricas filtradas por sección
3. Crawl directo → fallback con trafilatura.spider

Usa trafilatura para extraer texto limpio (sin CTAs, menús, footers).
"""

import logging
import random
import re
import time
from datetime import datetime, timezone

import feedparser
import trafilatura
from trafilatura.sitemaps import sitemap_search
from tqdm import tqdm

from src.data.scraping.cleaner import clean_article_text
from src.data.scraping.db import (
    compute_content_hash,
    is_already_scraped,
    is_duplicate_content,
    mark_as_scraped,
)
from src.data.scraping.robots import is_url_allowed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting con backoff exponencial
# ---------------------------------------------------------------------------

_BASE_DELAY_MIN = 1.0
_BASE_DELAY_MAX = 3.0
_BACKOFF_FACTOR = 2.0
_MAX_DELAY = 30.0


def _adaptive_sleep(consecutive_errors: int) -> None:
    """Espera adaptativa: aumenta el delay exponencialmente ante errores."""
    base = random.uniform(_BASE_DELAY_MIN, _BASE_DELAY_MAX)
    delay = min(base * (_BACKOFF_FACTOR ** consecutive_errors), _MAX_DELAY)
    if consecutive_errors > 0:
        logger.info("  Backoff: esperando %.1fs (%d errores consecutivos)", delay, consecutive_errors)
    time.sleep(delay)


# ---------------------------------------------------------------------------
# Extracción de artículos con Trafilatura
# ---------------------------------------------------------------------------


def extract_article(url: str, source: str, category: str) -> dict | None:
    """Descarga y extrae un artículo con Trafilatura."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return None

        # Extraer texto limpio (trafilatura elimina menús, CTAs, footers)
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        if not text or len(text) < 400:
            return None

        # Extraer metadatos (título, autores, fecha)
        metadata = trafilatura.extract_metadata(downloaded)

        # Limpieza adicional (firmas de periodista, bylines, etc.)
        authors = []
        if metadata and metadata.author:
            authors = [a.strip() for a in metadata.author.split(";") if a.strip()]
        text = clean_article_text(text, authors=authors)

        if len(text) < 400:
            return None

        # Deduplicación por contenido
        content_hash = compute_content_hash(text)
        if is_duplicate_content(content_hash):
            logger.debug("Contenido duplicado: %s", url)
            return None

        scraped_at = datetime.now(timezone.utc).isoformat()
        mark_as_scraped(url, content_hash, source, category, scraped_at)

        title = metadata.title if metadata and metadata.title else ""
        date = metadata.date if metadata and metadata.date else None

        return {
            "text": text,
            "title": title,
            "authors": authors,
            "source": source,
            "category": category,
            "url": url,
            "date": date,
            "scraped_at": scraped_at,
        }
    except Exception:
        logger.warning("Error extrayendo %s", url)
        return None


# ---------------------------------------------------------------------------
# Descubrimiento de URLs
# ---------------------------------------------------------------------------


def _filter_political_urls(urls: list[str], url_filters: list[str]) -> list[str]:
    """Filtra URLs que contienen alguna de las secciones políticas."""
    if not url_filters:
        return urls
    pattern = re.compile("|".join(re.escape(f) for f in url_filters), re.IGNORECASE)
    return [url for url in urls if pattern.search(url)]


def discover_urls_rss(feeds: list[str]) -> list[str]:
    """Descubre URLs desde feeds RSS."""
    urls: list[str] = []
    seen: set[str] = set()

    for feed_url in feeds:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = entry.get("link", "")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
        except Exception:
            logger.warning("Error parseando RSS %s", feed_url)

    return urls


def discover_urls_sitemap(base_url: str, url_filters: list[str]) -> list[str]:
    """Descubre URLs desde sitemap.xml, filtradas por sección política."""
    try:
        all_urls = sitemap_search(base_url)
        if not all_urls:
            return []
        return _filter_political_urls(list(all_urls), url_filters)
    except Exception:
        logger.warning("Error leyendo sitemap de %s", base_url)
        return []


def discover_urls_crawl(base_url: str) -> list[str]:
    """Fallback: descubre URLs crawleando la página principal."""
    try:
        downloaded = trafilatura.fetch_url(base_url)
        if downloaded is None:
            return []
        # Extraer todos los links de la página
        from courlan import extract_links
        links = extract_links(downloaded, base_url)
        return list(links) if links else []
    except Exception:
        logger.warning("Error crawleando %s", base_url)
        return []


# ---------------------------------------------------------------------------
# Scraping de una fuente completa
# ---------------------------------------------------------------------------


def scrape_source(
    name: str,
    source_config: dict,
    max_articles: int,
) -> list[dict]:
    """Scrapea una fuente siguiendo su estrategia configurada.

    Prioridad: RSS → Sitemap → Crawl
    """
    url = source_config["url"]
    category = source_config["category"]
    mode = source_config["mode"]
    url_filters = source_config.get("url_filters", [])
    rss_feeds = source_config.get("rss_feeds", [])

    # 1. Descubrir URLs
    candidate_urls: list[str] = []

    # Intentar RSS primero
    if rss_feeds:
        rss_urls = discover_urls_rss(rss_feeds)
        logger.info("  RSS: %d URLs encontradas", len(rss_urls))
        candidate_urls.extend(rss_urls)

    # Sitemap (si no tenemos suficientes URLs o como complemento)
    if len(candidate_urls) < max_articles:
        sitemap_urls = discover_urls_sitemap(url, url_filters if mode == "sitemap" else [])
        # Deduplicar contra URLs de RSS
        existing = set(candidate_urls)
        new_sitemap = [u for u in sitemap_urls if u not in existing]
        logger.info("  Sitemap: %d URLs encontradas (%d nuevas)", len(sitemap_urls), len(new_sitemap))
        candidate_urls.extend(new_sitemap)

    # Fallback: crawl de la página
    if not candidate_urls:
        crawl_urls = discover_urls_crawl(url)
        if mode == "sitemap":
            crawl_urls = _filter_political_urls(crawl_urls, url_filters)
        logger.info("  Crawl (fallback): %d URLs encontradas", len(crawl_urls))
        candidate_urls = crawl_urls

    if not candidate_urls:
        logger.warning("  No se encontraron URLs para %s", name)
        return []

    # Limitar candidatos
    random.shuffle(candidate_urls)
    candidate_urls = candidate_urls[:max_articles * 2]  # margen por errores/duplicados

    # 2. Extraer artículos
    articles: list[dict] = []
    skipped = 0
    blocked = 0
    consecutive_errors = 0

    pbar = tqdm(
        candidate_urls,
        desc=f"  {name}",
        unit="art",
        leave=True,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}",
    )

    for article_url in pbar:
        if len(articles) >= max_articles:
            break

        pbar.set_postfix_str(f"{len(articles)} nuevos, {skipped} dup, {blocked} robot")

        if is_already_scraped(article_url):
            skipped += 1
            continue

        if not is_url_allowed(article_url):
            blocked += 1
            continue

        data = extract_article(article_url, name, category)
        if data:
            articles.append(data)
            consecutive_errors = 0
        else:
            consecutive_errors += 1

        _adaptive_sleep(consecutive_errors)

    pbar.close()
    logger.info(
        "  → %d nuevos, %d duplicados, %d bloqueados de %s",
        len(articles), skipped, blocked, name,
    )
    return articles
