"""Verificación de robots.txt para cumplimiento ético del scraping.

Consulta el archivo robots.txt de cada medio y verifica si una URL
está permitida antes de descargarla. Fundamental para rigor metodológico
en el trabajo de grado.
"""

import logging
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

logger = logging.getLogger(__name__)

# User-Agent genérico para consultar robots.txt
_BOT_NAME = "*"


@lru_cache(maxsize=64)
def _get_robot_parser(base_url: str) -> RobotFileParser | None:
    """Descarga y parsea el robots.txt de un dominio (cacheado por dominio)."""
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        rp.read()
        return rp
    except Exception:
        logger.warning("No se pudo leer robots.txt de %s", robots_url)
        # Si no se puede leer, se permite el scraping por defecto
        return None


def is_url_allowed(url: str) -> bool:
    """Verifica si una URL está permitida según el robots.txt del dominio."""
    parser = _get_robot_parser(url)
    if parser is None:
        # Sin robots.txt accesible → se asume permitido
        return True
    return parser.can_fetch(_BOT_NAME, url)
