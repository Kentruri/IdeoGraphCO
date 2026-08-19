"""Configuración de headers HTTP para scraping de medios colombianos."""

import random
from urllib.parse import urlparse

# User-Agents reales y recientes para rotación (Chrome, Firefox, Safari, Edge)
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]


# User-Agent genérico de cliente HTTP (no navegador).
_GENERIC_UA = "curl/8.4.0"

# Dominios que INVIERTEN la lógica habitual: rechazan User-Agents de navegador
# con 403 y sirven 200 a un cliente HTTP genérico, de modo que la rotación
# normal los vuelve inservibles. Se les fija un UA en este mapa.
#
# Está vacío a propósito: los dos casos conocidos (france24.com y rfi.fr, ambos
# 403 con UA de Chrome y 200 sin él, ago-2026) salieron del catálogo al
# restringirlo a prensa colombiana. El mecanismo se mantiene porque
# scripts/verify_sources.py prueba dominios candidatos que aún no están
# registrados, y porque el patrón reaparece en sitios detrás de ciertos WAF.
DOMAIN_USER_AGENTS: dict[str, str] = {}


def get_random_user_agent() -> str:
    """Devuelve un User-Agent aleatorio para rotación."""
    return random.choice(USER_AGENTS)


def get_user_agent_for(url: str) -> str:
    """User-Agent para una URL: fijo si el dominio lo exige, aleatorio si no.

    Los dominios de `DOMAIN_USER_AGENTS` bloquean navegadores, por lo que la
    rotación normal los rompe. El resto rota como siempre.
    """
    host = urlparse(url).netloc.lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    for domain, user_agent in DOMAIN_USER_AGENTS.items():
        if host == domain or host.endswith("." + domain):
            return user_agent
    return get_random_user_agent()
