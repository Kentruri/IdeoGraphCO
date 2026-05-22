"""Pipeline completo del scraper: scrape → clean → filter en un solo paso.

Cada artículo pasa por las 3 etapas antes de escribirse a disco. Solo los que
pasan el filter LLM como "political_article" terminan en el archivo de salida.

Diseño:
- Escritura incremental al JSONL final (no carga todo en memoria)
- Deduplicación persistente vía scraper_history.db (idempotente entre runs)
- El cleaning regex ya está integrado en parser.extract_article()
- El filter LLM es opcional (--no-filter para iteraciones rápidas sin gastar API)
"""

import json
import logging
import random
import time
from pathlib import Path

from tqdm import tqdm

from src.scraper.article_filter import is_real_article
from src.scraper.cleaner import clean_article_text
from src.scraper.db import is_already_scraped
from src.scraper.parser import (
    _adaptive_sleep,
    _filter_political_urls,
    discover_urls_crawl,
    discover_urls_rss,
    discover_urls_sitemap,
    extract_article,
)
from src.scraper.robots import is_url_allowed

logger = logging.getLogger(__name__)


def discover_candidate_urls(
    name: str,
    source_config: dict,
    max_articles: int,
) -> list[str]:
    """Encuentra URLs candidatas para una fuente: RSS → sitemap → crawl."""
    url = source_config["url"]
    mode = source_config["mode"]
    url_filters = source_config.get("url_filters", [])
    rss_feeds = source_config.get("rss_feeds", [])

    candidate_urls: list[str] = []

    if rss_feeds:
        rss_urls = discover_urls_rss(rss_feeds)
        candidate_urls.extend(rss_urls)
        logger.info("  [%s] RSS: %d URLs", name, len(rss_urls))

    if len(candidate_urls) < max_articles * 2:
        sitemap_urls = discover_urls_sitemap(
            url, url_filters if mode == "sitemap" else [],
        )
        existing = set(candidate_urls)
        new = [u for u in sitemap_urls if u not in existing]
        candidate_urls.extend(new)
        logger.info("  [%s] Sitemap: %d (%d nuevas)", name, len(sitemap_urls), len(new))

    if not candidate_urls:
        crawl_urls = discover_urls_crawl(url)
        if mode == "sitemap":
            crawl_urls = _filter_political_urls(crawl_urls, url_filters)
        candidate_urls = crawl_urls
        logger.info("  [%s] Crawl fallback: %d URLs", name, len(crawl_urls))

    random.shuffle(candidate_urls)
    return candidate_urls[: max_articles * 2]


def process_url(
    article_url: str,
    source: str,
    category: str,
    llm_client,
    llm_model: str,
    min_chars: int,
    use_llm_filter: bool,
    filter_log_path: Path | None = None,
) -> tuple[dict | None, str]:
    """Procesa una URL: scrape + clean + filter. Retorna (article, motivo_si_skip).

    Si filter_log_path es dado, escribe una línea JSONL con la decisión del
    filter LLM (tanto keep como drop) para análisis posterior.
    """
    if is_already_scraped(article_url):
        return None, "dup"

    if not is_url_allowed(article_url):
        return None, "robot"

    article = extract_article(article_url, source, category)
    if article is None:
        return None, "scrape_fail"

    # Re-aplicar cleaner (idempotente). extract_article ya lo aplicó, pero
    # esto deja explícito que el cleaning forma parte del pipeline.
    article["text"] = clean_article_text(
        article["text"],
        source_name=source,
        authors=article.get("authors"),
    )
    if len(article["text"]) < min_chars:
        return None, "too_short"

    if use_llm_filter:
        is_political, info = is_real_article(llm_client, article["text"], llm_model)

        # Log estructurado: registra TODA decisión (keep + drop) con confidence
        # y reason. Permite analizar distribución y calibrar umbrales sin
        # parsear regex sobre stdout.
        if filter_log_path is not None and info is not None:
            append_filter_decision(filter_log_path, {
                "id": article.get("id"),
                "url": article_url,
                "source": source,
                "category": info.get("category"),
                "confidence": info.get("confidence"),
                "reason": info.get("reason"),
                "kept": is_political,
            })

        if not is_political:
            cat = (info or {}).get("category", "filter_fail")
            reason = (info or {}).get("reason", "")
            conf = (info or {}).get("confidence")
            if reason:
                conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
                logger.debug("Filter descartó [%s conf=%s] %s — %s",
                             cat, conf_str, article_url[:60], reason[:120])
            return None, f"filter:{cat}"

    return article, "kept"


def append_jsonl(path: Path, record: dict) -> None:
    """Escribe un registro al JSONL y hace flush para no perder en crashes."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def append_filter_decision(path: Path, record: dict) -> None:
    """Registra una decisión del filter LLM en JSONL.

    Cada línea es una decisión (keep o drop) con id, url, source, category,
    confidence, reason, kept. Útil para analizar después la distribución de
    confidence y calibrar umbrales sin re-correr el scraping.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


def scrape_pipeline(
    sources: dict[str, dict],
    output_path: Path,
    max_per_source: int = 50,
    use_llm_filter: bool = True,
    llm_client=None,
    llm_model: str = "gemini-2.5-flash-lite",
    min_chars: int = 800,
    rate_limit_filter: float = 4.5,
    only_sources: list[str] | None = None,
    filter_log_path: Path | None = None,
) -> dict[str, int]:
    """Corre el pipeline completo sobre las fuentes dadas.

    Args:
        sources: dict {name: source_config} (típicamente SOURCES de sources.py)
        output_path: archivo JSONL donde se appenden los artículos que pasan
        max_per_source: cuántos artículos máximo por fuente
        use_llm_filter: si True, filtra con LLM (cuesta API). Si False, solo
            scrape + clean (útil para tests)
        llm_client: cliente de google.genai.Client (requerido si use_llm_filter)
        llm_model: modelo del filter (default flash-lite, barato)
        min_chars: longitud mínima del texto post-cleaning
        rate_limit_filter: segundos a esperar entre llamadas LLM
        only_sources: si se da, solo procesa estas fuentes (default: todas)
        filter_log_path: si se da, registra cada decisión del filter LLM en
            ese JSONL (id, category, confidence, reason, kept). Útil para
            calibrar el filtro y analizar distribución de confianza.

    Returns:
        dict con contadores agregados: {kept, scrape_fail, dup, robot,
        too_short, filter:*}.
    """
    if use_llm_filter and llm_client is None:
        raise ValueError("use_llm_filter=True requiere llm_client")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    selected = (
        sources if not only_sources
        else {k: v for k, v in sources.items() if k in only_sources}
    )

    totals: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}

    print()
    print("=" * 60)
    print(f"  IdeoGraphCO — pipeline scrape+clean+filter")
    print(f"  Fuentes:        {len(selected)}")
    print(f"  Max/fuente:     {max_per_source}")
    print(f"  Filter LLM:     {'SÍ (' + llm_model + ')' if use_llm_filter else 'NO'}")
    print(f"  Min chars:      {min_chars}")
    print(f"  Salida:         {output_path}")
    print("=" * 60)
    print()

    for name, conf in selected.items():
        logger.info("→ Procesando fuente: %s", name)
        candidates = discover_candidate_urls(name, conf, max_per_source)
        if not candidates:
            logger.warning("  Sin candidatos para %s", name)
            continue

        counts: dict[str, int] = {}
        pbar = tqdm(
            candidates,
            desc=f"  {name}",
            unit="art",
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}",
        )

        consecutive_errors = 0
        for article_url in pbar:
            if counts.get("kept", 0) >= max_per_source:
                break

            article, reason = process_url(
                article_url=article_url,
                source=name,
                category=conf["category"],
                llm_client=llm_client,
                llm_model=llm_model,
                min_chars=min_chars,
                use_llm_filter=use_llm_filter,
                filter_log_path=filter_log_path,
            )
            counts[reason] = counts.get(reason, 0) + 1

            if article is not None:
                append_jsonl(output_path, article)
                consecutive_errors = 0
            elif reason == "scrape_fail":
                consecutive_errors += 1

            pbar.set_postfix_str(
                f"keep={counts.get('kept',0)} dup={counts.get('dup',0)} "
                f"short={counts.get('too_short',0)} fail={consecutive_errors}"
            )

            # Sleep adaptativo entre URLs (más fuerte ante errores de scrape)
            _adaptive_sleep(consecutive_errors)

            # Rate limit adicional del LLM filter
            if use_llm_filter and reason != "dup":
                time.sleep(rate_limit_filter)

        pbar.close()
        by_source[name] = counts
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    print()
    print("=" * 60)
    print(f"  RESULTADO ({sum(totals.values())} URLs procesadas)")
    print(f"  ✓ Conservados:        {totals.get('kept', 0)}")
    print(f"  ⊘ Duplicados:         {totals.get('dup', 0)}")
    print(f"  ⊘ Robots.txt:         {totals.get('robot', 0)}")
    print(f"  ⊘ Scrape fail:        {totals.get('scrape_fail', 0)}")
    print(f"  ⊘ Muy cortos:         {totals.get('too_short', 0)}")
    for k, v in sorted(totals.items()):
        if k.startswith("filter:"):
            print(f"  ⊘ {k:20} {v}")
    print(f"  Salida:               {output_path}")
    print("=" * 60)
    print()

    return totals
