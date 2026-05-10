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
# Cookie banners y prompts de paywall (común en El Tiempo y otros medios)
# ---------------------------------------------------------------------------

# Bloque de cookie banner: desde "En este portal utilizamos..." hasta el final
# del bloque (suele ser un párrafo). Usa lookhead para no comerse contenido real.
_COOKIE_BANNER_PATTERN = re.compile(
    r"En este portal utilizamos datos de navegación.*?"
    r"(?:aceptando esta utilización\.?|Puede conocer cómo deshabilitarlas[^\n]*|aquí)",
    re.DOTALL,
)

# Prompts de paywall / suscripción
_PAYWALL_PATTERN = re.compile(
    r"(?:"
    r"Ya tienes una cuenta vinculada a [A-Z\s]+,\s*por favor inicia sesión[^\n]*"
    r"|¡Hola! Parece que has alcanzado tu límite[^\n]*"
    r"|¿Quieres seguir disfrutando de este y otros beneficios[^\n]*"
    r"|Adquiere el plan de suscripción[^\n]*"
    r"|¡Hola! Haz? excedido el máximo de peticiones[^\n]*"
    r"|Para más información continua navegando en[^\n]*"
    r")",
)

# Mensajes de error y UI de chatbot
_UI_NOISE_PATTERN = re.compile(
    r"(?:"
    r"Error \d{3}\s*\n[^\n]*"
    r"|Estamos resolviendo el problema[^\n]*"
    r"|Procesando tu pregunta[^\n]*"
    r"|¿Sabías que registrándote en nuestro portal[^\n]*"
    r"|Con el envío de tus consultas, aceptas los Términos[^\n]*"
    r"|Recuerda que las respuestas generadas pueden presentar inexactitudes[^\n]*"
    r"|De acuerdo con las políticas de la IA[^\n]*"
    r"|no es posible responder a las preguntas relacionadas[^\n]*"
    r")",
)

# ---------------------------------------------------------------------------
# Listings de noticias relacionadas (página de homepage en vez de artículo)
# Cuando trafilatura captura mal el artículo y trae un listado de titulares.
# ---------------------------------------------------------------------------

# Marcadores que indican el inicio de una sección de listado (cortar de aquí)
_SECTION_CUTOFF_PATTERN = re.compile(
    r"\n\s*"
    r"(?:Más para ver|Nuestro mundo|Más noticias|Lo más leído|Lo último|"
    r"Más sobre|También en [A-Z]|Tendencias|En portada|Otras noticias|"
    r"Horóscopo\s*\n|Crucigrama\s*\n|"
    # Bloques de promoción de El Tiempo (paywall)
    r"BOLETINES EL TIEMPO|EL TIEMPO GOOGLE NEWS|EL TIEMPO WHATSAPP|"
    r"EL TIEMPO APP|SUSCRÍBETE AL DIGITAL|"
    # Footers de redes
    r"Sigue toda la información de [A-Z][^\n]{1,50} en Facebook|"
    r"Conforme a los criterios de\s*$)"
    r".*$",
    re.DOTALL,
)

# ---------------------------------------------------------------------------
# Inicio de artículo: marcador que indica donde empieza el contenido real.
# Si encontramos "Noticia\n" o "Análisis\n" al inicio, descartamos todo lo previo.
# Útil para El Tiempo que prefija con cookie banner + chatbot UI antes del artículo.
# ---------------------------------------------------------------------------

_ARTICLE_START_MARKER = re.compile(
    r"\A.*?\n\s*"
    r"(?:Noticia|Análisis|Opinión|Editorial|Reportaje|Crónica|Entrevista|"
    r"Exclusivo suscriptores)\s*\n",
    re.DOTALL,
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
    1. Cookie banners de medios
    2. Prompts de paywall / suscripción
    3. UI de chatbot y errores
    4. Bloques CTA ("LEA TAMBIÉN\n\ntítulo", "Lea:", "Ver más:")
    5. Frases CTA inline
    6. CTAs de WhatsApp/redes sociales
    7. Firmas de periodista al final
    8. Emails al final
    9. Footers de marca (PORTAFOLIO, etc.)
    10. Listings de noticias relacionadas (corte de sección)
    11. Líneas con solo el nombre del autor
    12. Normalización de espacios
    """
    # 0. Si hay marcador de inicio de artículo ("Noticia\n", "Análisis\n", etc.),
    # descartar todo lo previo (cookie banner, paywall, UI de chatbot).
    text = _ARTICLE_START_MARKER.sub("", text, count=1)

    # 1-3. Limpieza preliminar de UI/banners restantes
    text = _COOKIE_BANNER_PATTERN.sub("", text)
    text = _PAYWALL_PATTERN.sub("", text)
    text = _UI_NOISE_PATTERN.sub("", text)

    # 4-6. CTAs
    text = _CTA_BLOCK_PATTERN.sub("", text)
    text = _CTA_INLINE_PATTERN.sub("", text)
    text = _SOCIAL_CTA_PATTERN.sub("", text)

    # 7-9. Firmas y footers al final
    text = _SIGNATURE_PATTERN.sub("", text)
    text = _EMAIL_TAIL_PATTERN.sub("", text)
    text = _BRAND_FOOTER_PATTERN.sub("", text)

    # 10. Cortar desde "Más para ver", "Nuestro mundo", etc.
    text = _SECTION_CUTOFF_PATTERN.sub("", text)

    # 11. Nombres de autores sueltos
    if authors:
        text = _remove_author_lines(text, authors)

    # 12. Normalizar espacios
    text = _TRAILING_SPACES.sub("", text)
    text = _MULTI_NEWLINES.sub("\n\n", text)
    text = text.strip()

    return text
