"""Descubridor complementario de URLs vía GDELT DOC 2.0 (gratis, sin API key).

GDELT monitorea prensa colombiana más allá del catálogo de sources.py. Este
módulo consulta artículos recientes (`sourcecountry:CO sourcelang:spanish` +
términos políticos) y:
- URLs cuyo dominio SÍ está en el catálogo → se suman como candidatas de esa
  fuente (mejora cobertura/frescura sin romper la categorización).
- Dominios desconocidos → se registran en logs/gdelt_unknown_domains.jsonl
  para curaduría manual (posibles fuentes nuevas para sources.py).

Límite informal de GDELT: ~1 request cada 5s por IP. Aquí se hace UNA sola
consulta por corrida.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from src.scraper.urls import domain_of, normalize_url

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Términos amplios de política colombiana; el filter LLM aguas abajo es
# quien decide politicidad — aquí solo se acota el ruido.
DEFAULT_QUERY_TERMS: list[str] = [
    "gobierno", "congreso", "senado", "presidente", "reforma",
    "elecciones", "ministro", "corte", "fiscalia", "paz",
]

_REQUEST_TIMEOUT_SECONDS = 30
_USER_AGENT = "IdeoGraphCO-Research/1.0 (trabajo de grado; contacto en el repo)"


def build_query(terms: list[str] | None = None) -> str:
    terms = terms or DEFAULT_QUERY_TERMS
    joined = " OR ".join(terms)
    return f"({joined}) sourcecountry:CO sourcelang:spanish"


def parse_artlist(payload: dict) -> list[dict]:
    """Extrae candidatos del JSON de GDELT (modo artlist)."""
    candidates: list[dict] = []
    for item in payload.get("articles", []):
        url = item.get("url", "")
        if not url:
            continue
        candidates.append({
            "url": normalize_url(url),
            "title": item.get("title", ""),
            "domain": domain_of(url),
            "seendate": item.get("seendate", ""),
        })
    return candidates


def fetch_candidates(
    terms: list[str] | None = None,
    timespan: str = "3d",
    max_records: int = 250,
) -> list[dict]:
    """Consulta GDELT DOC 2.0 y devuelve candidatos [{url, title, domain, seendate}]."""
    params = urllib.parse.urlencode({
        "query": build_query(terms),
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": timespan,
        "sort": "datedesc",
    })
    request = urllib.request.Request(
        f"{GDELT_DOC_API}?{params}",
        headers={"User-Agent": _USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        logger.warning("GDELT no disponible: %s", str(e)[:200])
        return []
    return parse_artlist(payload)


def map_candidates_to_sources(
    candidates: list[dict],
    sources: dict[str, dict],
    unknown_log_path: Path | None = None,
) -> dict[str, list[str]]:
    """Asigna cada candidato a la fuente del catálogo cuyo dominio coincide.

    Los dominios desconocidos NO se scrapean (mantiene limpia la
    categorización por fuente); se loguean para curaduría.
    """
    domain_to_source = {
        domain_of(config["url"]): name for name, config in sources.items()
    }

    by_source: dict[str, list[str]] = {}
    unknown: list[dict] = []
    for candidate in candidates:
        source_name = domain_to_source.get(candidate["domain"])
        if source_name:
            by_source.setdefault(source_name, []).append(candidate["url"])
        else:
            unknown.append(candidate)

    if unknown and unknown_log_path is not None:
        unknown_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(unknown_log_path, "a", encoding="utf-8") as f:
            for candidate in unknown:
                f.write(json.dumps(candidate, ensure_ascii=False) + "\n")
        top_domains = Counter(c["domain"] for c in unknown).most_common(8)
        logger.info(
            "GDELT: %d URLs de dominios fuera del catálogo → %s "
            "(top: %s) — candidatos a fuentes nuevas",
            len(unknown), unknown_log_path,
            ", ".join(f"{d}×{n}" for d, n in top_domains),
        )

    total_mapped = sum(len(urls) for urls in by_source.values())
    logger.info(
        "GDELT: %d candidatos mapeados a %d fuentes del catálogo",
        total_mapped, len(by_source),
    )
    return by_source
