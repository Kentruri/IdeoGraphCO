"""Pipeline completo del scraper: scrape → clean → prefilter → filter LLM.

Cada artículo pasa por las etapas antes de escribirse a disco. Solo los que
pasan el filtro como "political_article" terminan en el archivo de salida.

Diseño:
- Escritura incremental al JSONL final (no carga todo en memoria); appends
  protegidos con lock (soporta workers en paralelo).
- Deduplicación persistente vía scraper_history.db, con semántica corregida:
  las URLs se marcan como procesadas SOLO en desenlaces definitivos
  (persistido, no-político, muy corto, contenido duplicado). Un fallo de
  scraping o del LLM NO quema la URL — se reintenta en la próxima corrida.
- Frescura primero: RSS → news-sitemaps (ordenados por fecha) → candidatas
  externas (GDELT) → sitemap histórico (barajado) → crawl.
- Prefilter local opcional (TF-IDF + LR entrenado con las decisiones del
  propio LLM): resuelve los casos obvios gratis; solo la zona gris paga API.
- Paralelización por fuente (--workers N): la extracción es I/O-bound; el
  filter LLM se serializa con un rate limiter global (free tier de Gemini).
"""

import json
import logging
import random
import threading
import time
from pathlib import Path

from tqdm import tqdm

from src.scraper.article_filter import is_real_article
from src.scraper.cleaner import clean_article_text
from src.scraper.db import is_already_scraped, is_duplicate_content, mark_as_scraped
from src.scraper.parser import (
    _adaptive_sleep,
    _filter_political_urls,
    discover_urls_crawl,
    discover_urls_news_sitemap,
    discover_urls_rss,
    discover_urls_sitemap,
    extract_article,
)
from src.scraper.prefilter import PoliticalPrefilter
from src.scraper.quality import assess_article_quality
from src.scraper.robots import is_url_allowed
from src.scraper.urls import dedupe_normalized

logger = logging.getLogger(__name__)

# Los appends al JSONL y al filter-log se serializan (varias fuentes en
# paralelo escriben al mismo archivo).
_WRITE_LOCK = threading.Lock()

# Primeros N caracteres del texto que se guardan en el filter-log: son el
# dataset de entrenamiento del prefilter (scripts/train_prefilter.py).
_TEXT_HEAD_CHARS = 3000


class LLMRateLimiter:
    """Serializa las llamadas al LLM entre hilos respetando el intervalo."""

    def __init__(self, min_interval_seconds: float):
        self._interval = min_interval_seconds
        self._lock = threading.Lock()
        self._last_call = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait_for = self._last_call + self._interval - now
            if wait_for > 0:
                time.sleep(wait_for)
            self._last_call = time.monotonic()


def discover_candidate_urls(
    name: str,
    source_config: dict,
    max_articles: int,
    extra_candidates: list[str] | None = None,
) -> list[str]:
    """Encuentra URLs candidatas priorizando FRESCURA.

    Orden: RSS (newest-first) → news-sitemaps con fecha → candidatas externas
    (GDELT) → sitemap histórico (barajado) → crawl. Todas normalizadas
    (sin utm_*, sin fragmento, sin slash final) y deduplicadas.
    """
    url = source_config["url"]
    mode = source_config["mode"]
    url_filters = source_config.get("url_filters", [])
    rss_feeds = source_config.get("rss_feeds", [])
    news_sitemaps = source_config.get("news_sitemaps", [])

    fresh: list[str] = []

    if rss_feeds:
        rss_urls = discover_urls_rss(rss_feeds)
        fresh.extend(rss_urls)
        logger.info("  [%s] RSS: %d URLs", name, len(rss_urls))

    if news_sitemaps:
        dated = discover_urls_news_sitemap(news_sitemaps)
        if mode == "sitemap":
            dated = _filter_political_urls(dated, url_filters)
        fresh.extend(dated)
        logger.info("  [%s] News-sitemap: %d URLs (orden por fecha)", name, len(dated))

    if extra_candidates:
        fresh.extend(extra_candidates)
        logger.info("  [%s] Externas (GDELT): %d URLs", name, len(extra_candidates))

    candidate_urls = dedupe_normalized(fresh)

    # Sitemap histórico solo si la frescura no alcanzó (se baraja: no trae
    # fechas y sirve para ampliar el dataset, no para lo último).
    if len(candidate_urls) < max_articles * 2:
        sitemap_urls = discover_urls_sitemap(
            url, url_filters if mode == "sitemap" else [],
        )
        random.shuffle(sitemap_urls)
        existing = set(candidate_urls)
        new = [u for u in dedupe_normalized(sitemap_urls) if u not in existing]
        candidate_urls.extend(new)
        logger.info("  [%s] Sitemap: %d (%d nuevas)", name, len(sitemap_urls), len(new))

    # Gastar el presupuesto de candidatas SOLO en URLs nuevas. Sin este filtro,
    # en corridas sucesivas el corte de max_articles*2 se llenaba de URLs ya
    # scrapeadas (el RSS repite lo fresco) y cada corrida rendía menos aunque
    # el archivo histórico tuviera material de sobra.
    budget = max_articles * 2
    unseen: list[str] = []
    for candidate in candidate_urls:
        if len(unseen) >= budget:
            break
        if not is_already_scraped(candidate):
            unseen.append(candidate)

    # Crawl si RSS+sitemap no aportaron suficientes candidatas NUEVAS: con
    # `not candidate_urls` las fuentes cuyo sitemap devuelve unas pocas URLs
    # inservibles (stale, de paginación) nunca llegaban al crawl.
    if len(unseen) < max_articles:
        crawl_urls = discover_urls_crawl(url)
        if mode == "sitemap":
            crawl_urls = _filter_political_urls(crawl_urls, url_filters)
        random.shuffle(crawl_urls)
        existing = set(unseen)
        new = [
            u for u in dedupe_normalized(crawl_urls)
            if u not in existing and not is_already_scraped(u)
        ]
        unseen.extend(new)
        logger.info("  [%s] Crawl fallback: %d (%d nuevas)", name, len(crawl_urls), len(new))

    return unseen[:budget]


def process_url(
    article_url: str,
    source: str,
    category: str,
    llm_client,
    llm_model: str,
    min_chars: int,
    use_llm_filter: bool,
    filter_log_path: Path | None = None,
    escalate_model: str | None = "gemini-2.5-flash",
    escalate_threshold: float = 0.7,
    prefilter: PoliticalPrefilter | None = None,
    rate_limiter: LLMRateLimiter | None = None,
) -> tuple[dict | None, str]:
    """Procesa una URL: scrape + clean + prefilter + filter. → (article, motivo).

    Semántica de marcado en la BD de dedup:
    - Desenlace DEFINITIVO (no-político, muy corto, contenido duplicado):
      se marca aquí para no re-procesar nunca.
    - Artículo CONSERVADO: lo marca el caller DESPUÉS de persistirlo
      (crash-safe: nunca queda una URL quemada sin artículo en disco).
    - Fallo transitorio (scrape_fail, filter_error): NO se marca — se
      reintenta en la siguiente corrida.
    """
    if is_already_scraped(article_url):
        return None, "dup"

    if not is_url_allowed(article_url):
        return None, "robot"

    article = extract_article(article_url, source, category)
    if article is None:
        return None, "scrape_fail"

    content_hash = article["content_hash"]

    # Re-aplicar cleaner (idempotente). extract_article ya lo aplicó, pero
    # esto deja explícito que el cleaning forma parte del pipeline.
    article["text"] = clean_article_text(
        article["text"],
        source_name=source,
        authors=article.get("authors"),
    )
    if len(article["text"]) < min_chars:
        mark_as_scraped(article_url, content_hash, source, category, article["scraped_at"])
        return None, "too_short"

    # Compuerta de calidad estructural (gratis): páginas de listado/sección,
    # prosa incompleta, texto no-artículo. Corre ANTES del LLM para no gastar
    # API en basura obvia. Desenlace definitivo → se marca.
    verdict = assess_article_quality(article.get("title", ""), article["text"])
    if not verdict.ok:
        mark_as_scraped(article_url, content_hash, source, category, article["scraped_at"])
        return None, f"low_quality:{verdict.reasons[0]}"

    if is_duplicate_content(content_hash):
        mark_as_scraped(article_url, content_hash, source, category, article["scraped_at"])
        return None, "dup_content"

    if use_llm_filter:
        # --- Etapa 0: prefilter local (gratis) ---
        if prefilter is not None:
            decision = prefilter.decide(article["text"])
            if decision.action != "uncertain":
                if filter_log_path is not None:
                    append_filter_decision(filter_log_path, {
                        "id": article.get("id"),
                        "url": article_url,
                        "source": source,
                        "engine": "prefilter",
                        "category": (
                            "political_article" if decision.action == "keep"
                            else "nonpolitical_article"
                        ),
                        "confidence": round(decision.probability, 4),
                        "reason": f"prefilter p={decision.probability:.3f}",
                        "kept": decision.action == "keep",
                        "escalated": False,
                        "text_head": article["text"][:_TEXT_HEAD_CHARS],
                    })
                if decision.action == "drop":
                    mark_as_scraped(
                        article_url, content_hash, source, category, article["scraped_at"],
                    )
                    return None, "prefilter_drop"
                return article, "kept_prefilter"

        # --- Etapa 1: filter LLM (zona gris o sin prefilter) ---
        if rate_limiter is not None:
            rate_limiter.wait()
        is_political, info = is_real_article(
            llm_client,
            article["text"],
            model=llm_model,
            escalate_model=escalate_model,
            escalate_threshold=escalate_threshold,
        )

        # Fallo del LLM (cuota/servicio/parseo) ≠ "no político": la URL no se
        # marca y se reintenta en la próxima corrida.
        if info is None:
            return None, "filter_error"

        # Log estructurado: TODA decisión (keep + drop) con confidence, reason
        # y text_head — el text_head es el dataset del prefilter.
        if filter_log_path is not None:
            append_filter_decision(filter_log_path, {
                "id": article.get("id"),
                "url": article_url,
                "source": source,
                "engine": "llm",
                "category": info.get("category"),
                "confidence": info.get("confidence"),
                "reason": info.get("reason"),
                "kept": is_political,
                "escalated": info.get("escalated", False),
                "primary_confidence": info.get("primary_confidence"),
                "text_head": article["text"][:_TEXT_HEAD_CHARS],
            })

        if not is_political:
            cat = info.get("category", "?")
            reason = info.get("reason", "")
            conf = info.get("confidence")
            esc = info.get("escalated", False)
            if reason:
                conf_str = f"{conf:.2f}" if isinstance(conf, (int, float)) else "?"
                esc_tag = " [escalated]" if esc else ""
                logger.debug("Filter descartó [%s conf=%s]%s %s — %s",
                             cat, conf_str, esc_tag, article_url[:60], reason[:120])
            mark_as_scraped(
                article_url, content_hash, source, category, article["scraped_at"],
            )
            return None, f"filter:{cat}"

    return article, "kept"


def append_jsonl(path: Path, record: dict) -> None:
    """Escribe un registro al JSONL (con lock: soporta escritores en paralelo)."""
    with _WRITE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()


def load_existing_ids(path: Path) -> set[str]:
    """IDs ya presentes en el JSONL de salida.

    Segunda línea de defensa de la deduplicación: si scraper_history.db se
    pierde o desincroniza (clon fresco, DB borrada), el pipeline igual NO
    duplica artículos en el archivo de salida.
    """
    ids: set[str] = set()
    if not path.exists():
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record_id = json.loads(line).get("id")
            except json.JSONDecodeError:
                continue
            if record_id:
                ids.add(record_id)
    return ids


def append_filter_decision(path: Path, record: dict) -> None:
    """Registra una decisión del filtro (prefilter o LLM) en JSONL.

    Cada línea incluye id, url, source, engine, category, confidence, reason,
    kept y text_head (para entrenar/re-entrenar el prefilter).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with _WRITE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            f.flush()


def _process_source(
    name: str,
    conf: dict,
    output_path: Path,
    max_per_source: int,
    use_llm_filter: bool,
    llm_client,
    llm_model: str,
    min_chars: int,
    filter_log_path: Path | None,
    escalate_model: str | None,
    escalate_threshold: float,
    prefilter: PoliticalPrefilter | None,
    rate_limiter: LLMRateLimiter | None,
    extra_candidates: list[str] | None,
    show_progress: bool,
    existing_ids: set[str],
) -> dict[str, int]:
    """Procesa una fuente completa. Retorna contadores por motivo."""
    logger.info("→ Procesando fuente: %s", name)
    candidates = discover_candidate_urls(name, conf, max_per_source, extra_candidates)
    if not candidates:
        logger.warning("  Sin candidatos para %s", name)
        return {}

    counts: dict[str, int] = {}
    iterator = candidates
    pbar = None
    if show_progress:
        pbar = tqdm(
            candidates,
            desc=f"  {name}",
            unit="art",
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}] {postfix}",
        )
        iterator = pbar

    consecutive_errors = 0
    kept_key_total = 0
    for article_url in iterator:
        if kept_key_total >= max_per_source:
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
            escalate_model=escalate_model,
            escalate_threshold=escalate_threshold,
            prefilter=prefilter,
            rate_limiter=rate_limiter,
        )

        if article is not None:
            content_hash = article.pop("content_hash")
            # Guardia por ID contra el archivo de salida: aunque la BD de
            # dedup se haya perdido, el mismo artículo no se duplica.
            with _WRITE_LOCK:
                already_in_output = article["id"] in existing_ids
                if not already_in_output:
                    existing_ids.add(article["id"])
            if already_in_output:
                counts["dup_output"] = counts.get("dup_output", 0) + 1
                mark_as_scraped(
                    article["url"], content_hash, name, conf["category"],
                    article["scraped_at"],
                )
                _adaptive_sleep(0)
                continue
            append_jsonl(output_path, article)
            # Marcar DESPUÉS de persistir (crash-safe). Si crashea entre
            # ambos, la línea duplicada del JSONL la dedupe prepare_splits
            # por id; la URL se re-procesa una vez y queda marcada.
            mark_as_scraped(
                article["url"], content_hash, name, conf["category"],
                article["scraped_at"],
            )
            counts[reason] = counts.get(reason, 0) + 1
            kept_key_total += 1
            consecutive_errors = 0
        else:
            counts[reason] = counts.get(reason, 0) + 1
            if reason == "scrape_fail":
                consecutive_errors += 1

        if pbar is not None:
            pbar.set_postfix_str(
                f"keep={kept_key_total} dup={counts.get('dup', 0)} "
                f"pre={counts.get('prefilter_drop', 0)} fail={consecutive_errors}"
            )

        # Sleep adaptativo entre URLs (más fuerte ante errores de scrape).
        # El rate limit del LLM lo maneja LLMRateLimiter globalmente.
        _adaptive_sleep(consecutive_errors)

    if pbar is not None:
        pbar.close()
    return counts


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
    escalate_model: str | None = "gemini-2.5-flash",
    escalate_threshold: float = 0.7,
    prefilter: PoliticalPrefilter | None = None,
    workers: int = 1,
    extra_candidates_by_source: dict[str, list[str]] | None = None,
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
        rate_limit_filter: segundos mínimos entre llamadas LLM (global)
        only_sources: si se da, solo procesa estas fuentes (default: todas)
        filter_log_path: JSONL de decisiones del filtro (incluye text_head,
            que alimenta el entrenamiento del prefilter)
        prefilter: PoliticalPrefilter cargado (o None para solo-LLM)
        workers: fuentes procesadas en paralelo (1 = secuencial con barra;
            >1 desactiva tqdm y usa logs). La extracción es I/O-bound: 4-8
            acelera ~5x. El LLM sigue serializado por el rate limiter.
        extra_candidates_by_source: URLs externas (p.ej. GDELT) por fuente.

    Returns:
        dict con contadores agregados: {kept, kept_prefilter, prefilter_drop,
        scrape_fail, dup, dup_content, robot, too_short, filter_error, filter:*}.
    """
    if use_llm_filter and llm_client is None:
        raise ValueError("use_llm_filter=True requiere llm_client")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    selected = (
        sources if not only_sources
        else {k: v for k, v in sources.items() if k in only_sources}
    )
    extra_by_source = extra_candidates_by_source or {}

    if use_llm_filter and escalate_model:
        escalate_info = f"escalado: {escalate_model} si conf<{escalate_threshold}"
    elif use_llm_filter:
        escalate_info = "escalado: desactivado"
    else:
        escalate_info = "(filter LLM desactivado)"

    print()
    print("=" * 60)
    print("  IdeoGraphCO — pipeline scrape+clean+filter")
    print(f"  Fuentes:        {len(selected)}")
    print(f"  Max/fuente:     {max_per_source}")
    print(f"  Workers:        {workers}")
    print(f"  Filter LLM:     {'SÍ (' + llm_model + ')' if use_llm_filter else 'NO'}")
    print(f"  Prefilter:      {'SÍ' if prefilter is not None else 'NO'}")
    print(f"  Min chars:      {min_chars}")
    print(f"  {escalate_info}")
    print(f"  Salida:         {output_path}")
    if filter_log_path:
        print(f"  Filter log:     {filter_log_path}")
    print("=" * 60)
    print()

    rate_limiter = LLMRateLimiter(rate_limit_filter) if use_llm_filter else None
    show_progress = workers <= 1

    # Segunda línea de defensa del dedup: IDs ya presentes en la salida
    # (compartido entre hilos, protegido por _WRITE_LOCK)
    existing_ids = load_existing_ids(output_path)
    if existing_ids:
        logger.info("Salida existente: %d artículos ya en %s", len(existing_ids), output_path)

    totals: dict[str, int] = {}
    by_source: dict[str, dict[str, int]] = {}

    def _run(name: str, conf: dict) -> dict[str, int]:
        return _process_source(
            name=name,
            conf=conf,
            output_path=output_path,
            max_per_source=max_per_source,
            use_llm_filter=use_llm_filter,
            llm_client=llm_client,
            llm_model=llm_model,
            min_chars=min_chars,
            filter_log_path=filter_log_path,
            escalate_model=escalate_model,
            escalate_threshold=escalate_threshold,
            prefilter=prefilter,
            rate_limiter=rate_limiter,
            extra_candidates=extra_by_source.get(name),
            show_progress=show_progress,
            existing_ids=existing_ids,
        )

    if workers <= 1:
        for name, conf in selected.items():
            by_source[name] = _run(name, conf)
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_run, name, conf): name
                for name, conf in selected.items()
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    by_source[name] = future.result()
                except Exception:
                    logger.exception("Fuente %s falló", name)
                    by_source[name] = {"source_error": 1}

    for counts in by_source.values():
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    kept_total = totals.get("kept", 0) + totals.get("kept_prefilter", 0)
    print()
    print("=" * 60)
    print(f"  RESULTADO ({sum(totals.values())} URLs procesadas)")
    print(f"  ✓ Conservados:        {kept_total} "
          f"(LLM: {totals.get('kept', 0)}, prefilter: {totals.get('kept_prefilter', 0)})")
    print(f"  ⊘ Duplicados URL:     {totals.get('dup', 0)}")
    print(f"  ⊘ Duplicados cont.:   {totals.get('dup_content', 0)}")
    print(f"  ⊘ Ya en salida:       {totals.get('dup_output', 0)}")
    print(f"  ⊘ Prefilter drop:     {totals.get('prefilter_drop', 0)}")
    print(f"  ⊘ Robots.txt:         {totals.get('robot', 0)}")
    print(f"  ⊘ Scrape fail:        {totals.get('scrape_fail', 0)} (se reintentan)")
    print(f"  ⊘ Filter error:       {totals.get('filter_error', 0)} (se reintentan)")
    print(f"  ⊘ Muy cortos:         {totals.get('too_short', 0)}")
    for k, v in sorted(totals.items()):
        if k.startswith(("filter:", "low_quality:")):
            print(f"  ⊘ {k:20} {v}")
    print(f"  Salida:               {output_path}")
    print("=" * 60)
    print()

    return totals
