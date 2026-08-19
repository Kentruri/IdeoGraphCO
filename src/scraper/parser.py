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
import threading
import time
from datetime import datetime, timezone

import feedparser
import trafilatura
from trafilatura.settings import use_config
from trafilatura.sitemaps import sitemap_search
from tqdm import tqdm

from src.scraper.cleaner import clean_article_text
from src.scraper.config import get_user_agent_for
from src.scraper.db import (
    compute_content_hash,
    is_already_scraped,
    is_duplicate_content,
    mark_as_scraped,
)
from src.scraper.robots import is_url_allowed
from src.core.ids import article_id

# User-Agent identificable para requests de sitemaps (XML)
_SITEMAP_UA = "IdeoGraphCO-Research/1.0 (trabajo de grado)"

logger = logging.getLogger(__name__)

# Silenciar warnings ruidosos de trafilatura/courlan (links externos descartados,
# downloads fallidos, dominios divergentes). Solo dejar errores reales.
for noisy in ("courlan", "trafilatura", "htmldate", "trafilatura.metadata", "trafilatura.htmlprocessing"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

# Config de trafilatura con timeout para no quedar colgado en sitios lentos.
# THREAD-LOCAL: cada hilo del pipeline paralelo tiene su propia config (la
# config global de trafilatura no es thread-safe y el UA se rota por request).
_TLS = threading.local()


def _get_config():
    config = getattr(_TLS, "config", None)
    if config is None:
        config = use_config()
        config.set("DEFAULT", "DOWNLOAD_TIMEOUT", "15")
        config.set("DEFAULT", "EXTRACTION_TIMEOUT", "20")
        _TLS.config = config
    return config


def _set_user_agent(url: str):
    """Fija el User-Agent del config del hilo. Llamar antes de cada fetch_url.

    Rota entre navegadores salvo en los dominios que exigen un UA fijo
    (ver `DOMAIN_USER_AGENTS` en config.py).
    """
    config = _get_config()
    config.set("DEFAULT", "USER_AGENTS", get_user_agent_for(url))
    return config

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
    """Descarga y extrae un artículo con Trafilatura.

    Cada llamada rota el User-Agent (lista en src/scraper/config.py) para
    minimizar el riesgo de baneo por patrón uniforme, salvo en los dominios
    que exigen un UA fijo.
    """
    try:
        # Fijar UA antes de cada request (config por hilo)
        config = _set_user_agent(url)

        # Timeout explícito de 15s para no quedar colgado en sitios lentos
        downloaded = trafilatura.fetch_url(url, config=config)
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
        text = clean_article_text(text, source_name=source, authors=authors)

        if len(text) < 400:
            return None

        # Hash de contenido para dedup — la DECISIÓN de dedup y el marcado en
        # la BD ahora son del caller (pipeline): antes se marcaba aquí, ANTES
        # del filtro LLM y de escribir a disco, así que un crash o un fallo
        # del filtro dejaba la URL "quemada" sin artículo persistido.
        content_hash = compute_content_hash(text)

        scraped_at = datetime.now(timezone.utc).isoformat()

        title = metadata.title if metadata and metadata.title else ""
        date = metadata.date if metadata and metadata.date else None

        return {
            "id": article_id(url),
            "text": text,
            "title": title,
            "authors": authors,
            "source": source,
            "category": category,
            "url": url,
            "date": date,
            "scraped_at": scraped_at,
            # Interno (el pipeline lo consume y lo remueve antes de persistir)
            "content_hash": content_hash,
        }
    except TimeoutError as e:
        # Servidor lento o cuelga. No bloquear el resto del scrape.
        logger.warning("Timeout extrayendo %s: %s", url, e)
        return None
    except (ConnectionError, OSError) as e:
        # Errores de red (DNS, conexión rechazada, etc.).
        logger.warning("Error de red en %s: %s", url, e)
        return None
    except Exception as e:
        # Cualquier otro error (parsing, encoding, atributos inesperados de
        # trafilatura). Loggeamos el tipo para poder diagnosticar después.
        logger.warning("Error inesperado extrayendo %s (%s): %s",
                       url, type(e).__name__, str(e)[:120])
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


def discover_urls_sitemap(
    base_url: str, url_filters: list[str], timeout: int = 30,
) -> list[str]:
    """Descubre URLs desde sitemap.xml, filtradas por sección política.

    Usa timeout via threading para evitar quedarse colgado en sitemaps gigantes
    o sitios sin sitemap accesible.
    """
    import threading

    result: list[str] = []
    error: list[str] = []

    def _search() -> None:
        try:
            all_urls = sitemap_search(base_url)
            if all_urls:
                result.extend(_filter_political_urls(list(all_urls), url_filters))
        except Exception as e:
            error.append(str(e))

    thread = threading.Thread(target=_search, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        logger.warning("Sitemap de %s timeout después de %ds, saltando", base_url, timeout)
        return []
    if error:
        logger.warning("Error leyendo sitemap de %s: %s", base_url, error[0][:100])
        return []
    return result


def parse_news_sitemap_xml(xml_text: str) -> list[tuple[str, str]]:
    """Parsea un news-sitemap y devuelve [(url, fecha_iso)] SIN ordenar.

    Soporta `<lastmod>` estándar y `<news:publication_date>` (Google News).
    Entradas sin fecha reciben cadena vacía (se ordenan al final).
    """
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        logger.warning("News-sitemap XML inválido: %s", str(e)[:100])
        return []

    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    entries: list[tuple[str, str]] = []
    for url_el in root:
        if _local(url_el.tag) != "url":
            continue
        loc, date = "", ""
        for child in url_el.iter():
            tag = _local(child.tag)
            text = (child.text or "").strip()
            if tag == "loc" and not loc:
                loc = text
            elif tag in ("lastmod", "publication_date") and text:
                # publication_date (Google News) gana sobre lastmod
                if tag == "publication_date" or not date:
                    date = text
        if loc:
            entries.append((loc, date))
    return entries


def discover_urls_news_sitemap(sitemap_urls: list[str]) -> list[str]:
    """Descubre URLs desde news-sitemaps, ordenadas por fecha DESC (frescura).

    A diferencia del sitemap histórico (trafilatura, sin fechas, se baraja),
    los news-sitemaps traen `<lastmod>`/`<news:publication_date>`: lo más
    nuevo primero. Es la vía correcta de frescura para fuentes sin RSS.
    """
    import urllib.request

    entries: list[tuple[str, str]] = []
    for sitemap_url in sitemap_urls:
        try:
            request = urllib.request.Request(
                sitemap_url, headers={"User-Agent": _SITEMAP_UA},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                xml_text = response.read().decode("utf-8", errors="ignore")
            entries.extend(parse_news_sitemap_xml(xml_text))
        except Exception as e:
            logger.warning("Error leyendo news-sitemap %s: %s", sitemap_url, str(e)[:100])

    entries.sort(key=lambda pair: pair[1], reverse=True)
    seen: set[str] = set()
    urls: list[str] = []
    for url, _date in entries:
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def discover_urls_crawl(base_url: str) -> list[str]:
    """Fallback: descubre URLs crawleando la página principal."""
    try:
        # Mismo UA/timeout que extract_article: sin config, el crawl fallaba
        # con 403 justo en los dominios que exigen UA fijo.
        config = _set_user_agent(base_url)
        downloaded = trafilatura.fetch_url(base_url, config=config)
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

    # Sitemap solo si RSS no dio suficientes
    # (con max_articles*2 como margen para errores/duplicados)
    if len(candidate_urls) < max_articles * 2:
        logger.info("  Buscando sitemap (timeout 30s)...")
        sitemap_urls = discover_urls_sitemap(
            url, url_filters if mode == "sitemap" else [],
        )
        existing = set(candidate_urls)
        new_sitemap = [u for u in sitemap_urls if u not in existing]
        logger.info("  Sitemap: %d URLs (%d nuevas)", len(sitemap_urls), len(new_sitemap))
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

        # URL truncada para que el log no sea ilegible
        url_short = article_url if len(article_url) <= 90 else article_url[:87] + "..."

        if is_already_scraped(article_url):
            logger.info("  [%s] DUP  %s", name, url_short)
            skipped += 1
            continue

        if not is_url_allowed(article_url):
            logger.info("  [%s] ROBOT %s", name, url_short)
            blocked += 1
            continue

        data = extract_article(article_url, name, category)
        if data:
            # Dedup por contenido + marcado (extract_article ya no toca la BD)
            content_hash = data.pop("content_hash")
            if is_duplicate_content(content_hash):
                logger.info("  [%s] DUP-CONTENIDO %s", name, url_short)
                mark_as_scraped(
                    article_url, content_hash, name, category, data["scraped_at"],
                )
                skipped += 1
            else:
                mark_as_scraped(
                    article_url, content_hash, name, category, data["scraped_at"],
                )
                logger.info(
                    "  [%s] OK   %d chars — %s",
                    name, len(data["text"]), url_short,
                )
                articles.append(data)
            consecutive_errors = 0
        else:
            logger.info("  [%s] FAIL %s", name, url_short)
            consecutive_errors += 1

        _adaptive_sleep(consecutive_errors)

    pbar.close()
    logger.info(
        "  → %d nuevos, %d duplicados, %d bloqueados de %s",
        len(articles), skipped, blocked, name,
    )
    return articles
