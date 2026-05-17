"""IDs estables y deterministas para artículos.

El ID se deriva del URL: misma URL → mismo ID siempre. Esto permite enlazar
un artículo a través de todas las etapas del pipeline (scraping → cleaning →
filtering → labeling → splits) y entre múltiples corridas de scraping.

Formato: 16 caracteres hexadecimales (64 bits) del SHA-256 del URL.
A esa longitud, la probabilidad de colisión para 40k artículos es ~10⁻⁹.
"""

import hashlib

ID_LENGTH = 16


def article_id(url: str) -> str:
    """ID determinista de 16 chars hex desde el URL del artículo."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:ID_LENGTH]
