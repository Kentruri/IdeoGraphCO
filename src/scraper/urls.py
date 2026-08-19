"""Normalización de URLs para deduplicación e IDs estables.

Sin esto, la misma nota con `?utm_source=twitter` o con slash final genera
IDs distintos y entradas duplicadas en el histórico de dedup.

Nota de compatibilidad: los IDs existentes se derivaron de URLs SIN
normalizar. Un artículo viejo re-descubierto con parámetros de tracking
distintos se re-descargará UNA vez; el dedup por hash de contenido lo
atrapa y a partir de ahí queda registrado con su URL normalizada.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parámetros de tracking que no cambian el contenido de la página.
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "gclid", "fbclid", "msclkid", "igshid", "mc_cid", "mc_eid",
    "ref", "referrer", "source", "s", "smid", "sh", "outputType",
})
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_", "wt.", "pk_", "mtm_", "hsa_")


def _is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered in _TRACKING_PARAMS or lowered.startswith(_TRACKING_PREFIXES)


def normalize_url(url: str) -> str:
    """Canonicaliza una URL de artículo.

    - esquema y host en minúsculas; `http` → `https` NO se fuerza (algunos
      medios regionales solo sirven http)
    - elimina fragmento (#...) y parámetros de tracking (utm_*, fbclid, ...)
    - colapsa el slash final del path (excepto la raíz)
    """
    url = url.strip()
    if not url:
        return url
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.scheme or not parts.netloc:
        return url

    query_pairs = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(name)
    ]
    path = parts.path
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        path,
        urlencode(query_pairs),
        "",  # sin fragmento
    ))


def dedupe_normalized(urls: list[str]) -> list[str]:
    """Normaliza y deduplica preservando el orden de aparición."""
    seen: set[str] = set()
    out: list[str] = []
    for url in urls:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def domain_of(url: str) -> str:
    """Dominio sin `www.` (para mapear URLs externas a fuentes del catálogo)."""
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host
