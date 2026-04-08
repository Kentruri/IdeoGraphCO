"""Limpieza de texto de artículos scrapeados.

Remueve "frases parásito", firmas de periodistas, emails, CTAs,
footers de marca y otros fragmentos que no son contenido editorial.
NO convierte a minúsculas (el modelo ConfliBERT es Cased).
"""

import re

# ---------------------------------------------------------------------------
# Patrones de "frases parásito" (CTAs, referencias cruzadas)
# ---------------------------------------------------------------------------

# Bloque completo: frase + línea vacía + título de otra noticia
_CTA_BLOCK_PATTERN = re.compile(
    r"(?:LEA TAMBIÉN|Lea también|Lea:|Le puede interesar|Le recomendamos|"
    r"También le puede interesar|Puede leer:|Siga leyendo|"
    r"Ver más:|Ver también:|Leer más:|"
    r"Más noticias|Noticias relacionadas|Siga el minuto a minuto:?)"
    r"\s*\n\s*\n?"
    r"[^\n]{0,200}\n?",
    re.MULTILINE,
)

# Frases sueltas sin bloque (a veces aparecen inline)
_CTA_INLINE_PATTERN = re.compile(
    r"(?:LEA TAMBIÉN|Lea también|Lea:|Le puede interesar|Le recomendamos|"
    r"También le puede interesar|Puede leer:|Siga leyendo|"
    r"Ver más:|Ver también:|Leer más:):?\s*",
)

# ---------------------------------------------------------------------------
# CTAs de redes sociales y WhatsApp
# ---------------------------------------------------------------------------

_SOCIAL_CTA_PATTERN = re.compile(
    r"(?:"
    r"Haga clic aquí para seguirnos en WhatsApp"
    r"|Si desean? inscribirse"
    r"|Queremos tener una comunicación más directa"
    r"|Únete a nuestro canal de WhatsApp"
    r"|Síguenos en WhatsApp"
    r")[^\n]*\n?",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Firmas de periodistas al final del artículo
# ---------------------------------------------------------------------------

_SIGNATURE_PATTERN = re.compile(
    r"\n\s*"
    r"(?:"
    r"[A-ZÁÉÍÓÚÑ\s]{5,50}\s*\n\s*Periodista\s+de\s+[^\n]{1,80}\.?"
    r"|Redacción\s+[^\n]{1,50}\.?"
    r")"
    r"\s*$",
    re.MULTILINE,
)

# Emails al final del texto
_EMAIL_TAIL_PATTERN = re.compile(
    r"\n\s*[\w.+-]+@[\w-]+\.[\w.]+\s*$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Footers de marca (PORTAFOLIO, etc.)
# ---------------------------------------------------------------------------

_BRAND_FOOTER_PATTERN = re.compile(
    r"\n\s*(?:PORTAFOLIO|EL TIEMPO|EL ESPECTADOR|SEMANA)\s*$",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Nombres de autores repetidos en el cuerpo (bylines sueltas)
# ---------------------------------------------------------------------------


def _remove_author_lines(text: str, authors: list[str]) -> str:
    """Remueve líneas que solo contienen el nombre de un autor."""
    if not authors:
        return text
    lines = text.split("\n")
    cleaned = []
    author_names = {a.strip().lower() for a in authors if a.strip()}
    for line in lines:
        stripped = line.strip().lower()
        if stripped and stripped in author_names:
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Limpieza de espacios en blanco excesivos
# ---------------------------------------------------------------------------

_MULTI_NEWLINES = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)


def clean_article_text(text: str, authors: list[str] | None = None) -> str:
    """Limpia el texto de un artículo scrapeado.

    Aplica en orden:
    1. Remueve bloques CTA ("LEA TAMBIÉN\n\ntítulo", "Lea:", "Ver más:")
    2. Remueve frases CTA inline
    3. Remueve CTAs de WhatsApp/redes sociales
    4. Remueve firmas de periodista al final
    5. Remueve emails al final
    6. Remueve footers de marca (PORTAFOLIO, etc.)
    7. Remueve líneas con solo el nombre del autor
    8. Normaliza espacios en blanco
    """
    # 1. Bloques CTA
    text = _CTA_BLOCK_PATTERN.sub("", text)

    # 2. Frases CTA inline
    text = _CTA_INLINE_PATTERN.sub("", text)

    # 3. CTAs sociales
    text = _SOCIAL_CTA_PATTERN.sub("", text)

    # 4. Firmas al final
    text = _SIGNATURE_PATTERN.sub("", text)

    # 5. Emails al final
    text = _EMAIL_TAIL_PATTERN.sub("", text)

    # 6. Footers de marca
    text = _BRAND_FOOTER_PATTERN.sub("", text)

    # 7. Nombres de autores sueltos
    if authors:
        text = _remove_author_lines(text, authors)

    # 8. Normalizar espacios
    text = _TRAILING_SPACES.sub("", text)
    text = _MULTI_NEWLINES.sub("\n\n", text)
    text = text.strip()

    return text
