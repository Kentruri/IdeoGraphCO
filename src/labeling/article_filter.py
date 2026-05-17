"""LLM filter — decide si un texto es un artículo POLÍTICO bien formado.

Usa Gemini para clasificar cada texto en 6 categorías:
- "political_article": artículo de política / impacto estatal (CONSERVAR)
- "nonpolitical_article": artículo bien formado pero NO político (deportes,
  farándula, crónica roja sin implicación política, pieza de servicio)
- "garbage": menú, lista de URLs, sitemap, glosario, formulario
- "biography": biografía o página "acerca de"
- "static_page": página institucional sin valor noticioso
- "other": cualquier otro contenido no editorial

Solo se conservan los textos clasificados como "political_article".
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

FILTER_SYSTEM_PROMPT = """Eres un validador de contenido. Tu tarea es decidir si un texto es un artículo de noticia colombiano POLÍTICO bien formado, o si debe descartarse.

## CATEGORÍAS

- **political_article**: Artículo de noticia / opinión sobre política, gobierno, elecciones, justicia, conflicto armado, paz, reformas, políticas públicas, política internacional, política económica, orden público con implicación institucional, derechos humanos, controversias ambientales con dimensión política. Debe tener párrafos coherentes con narrativa periodística.
- **nonpolitical_article**: Artículo bien formado pero NO político: deportes, farándula y entretenimiento, crónica roja sin implicación política (accidentes de tráfico, robos comunes, asesinatos pasionales), piezas de servicio (tips legales, cortes de luz, horarios de transporte, vuelos), cultura sin dimensión política, recetas, salud sin política pública, ciencia y tecnología sin implicación gubernamental, convocatorias / concursos.
- **garbage**: Menús de navegación, listas de URLs, sitemaps en bruto, glosarios, listados de documentos sin redacción, formularios, contenido repetitivo sin coherencia narrativa.
- **biography**: Biografía o perfil de una persona como sujeto principal, página "Acerca de", "Quiénes somos".
- **static_page**: Página institucional estática (misión, visión, organigrama, equipo, contáctenos, mapa del sitio).
- **other**: Cualquier otro contenido editorial NO political_article ni clasificable arriba.

## REGLAS

1. Si trata de elecciones, candidatos, gobierno, congreso, cortes, fuerza pública con implicación política, conflicto armado, paz, reformas, políticas públicas o controversias institucionales → "political_article".
2. Si es un crimen, accidente o noticia local SIN implicación institucional/política → "nonpolitical_article".
3. Si describe a una persona individual como sujeto principal (biografía de senador, perfil de político) → "biography", aunque mencione política.
4. Si el texto es una sucesión de títulos/URLs/fechas sin redacción → "garbage".
5. Una noticia ambiental, económica o de seguridad se considera "political_article" SOLO si discute decisiones del Estado, controversias regulatorias, o tiene actores políticos como protagonistas. Si es solo informativa sin esa dimensión → "nonpolitical_article".
6. En caso de duda entre "political_article" y "nonpolitical_article" → escoge "nonpolitical_article" (preferimos descartar dudosos).
7. En caso de duda entre cualquier "_article" y "garbage" → escoge "garbage".

## FORMATO DE RESPUESTA (solo JSON, nada más)

{"is_political_article": true, "category": "political_article", "reason": "Reforma tributaria y debate en el Congreso"}

o

{"is_political_article": false, "category": "nonpolitical_article", "reason": "Accidente de tráfico sin implicación política"}
"""


def parse_filter_response(response_text: str) -> dict | None:
    """Extrae el JSON de la respuesta del LLM."""
    text = response_text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(
            "No se pudo parsear filter response (%s). Texto: %s",
            e, text[:400],
        )
        return None

    if "is_political_article" not in data or "category" not in data:
        return None

    return data


def call_filter_with_retry(
    client,
    model: str,
    text: str,
    max_retries: int = 3,
) -> str | None:
    """Llama al LLM filter con retry y backoff exponencial.

    Configuración para modelos 2.5 (reasoning):
    - response_mime_type=application/json → JSON garantizado
    - thinking_budget=0 → desactiva CoT interno (no necesario para esta tarea)
    """
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config={
                    "system_instruction": FILTER_SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    "thinking_config": {"thinking_budget": 0},
                    "max_output_tokens": 512,
                    "temperature": 0.0,
                },
            )
            return response.text
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "quota" in error_msg.lower():
                wait = 60
                logger.warning("Rate limit. Esperando %ds...", wait)
            else:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Error filter intento %d/%d: %s. Esperando %ds...",
                    attempt + 1, max_retries, error_msg[:100], wait,
                )
            time.sleep(wait)
    return None


def is_real_article(
    client,
    text: str,
    model: str = "gemini-2.5-flash-lite",
    max_chars: int = 1500,
) -> tuple[bool, dict | None]:
    """Pregunta al LLM si el texto es un artículo POLÍTICO real.

    Args:
        client: Cliente de Google GenAI.
        text: Texto del artículo.
        model: Modelo de Gemini a usar.
        max_chars: Caracteres iniciales del texto a enviar al LLM
            (suficiente para clasificar sin gastar tokens innecesarios).

    Returns:
        Tupla (es_político_artículo, info) donde info es el JSON parseado
        con campos is_political_article, category, reason. Solo retorna
        True si el texto es categoría "political_article".
    """
    truncated = text[:max_chars]
    response = call_filter_with_retry(client, model, truncated)
    if response is None:
        return False, None

    data = parse_filter_response(response)
    if data is None:
        return False, None

    return bool(data["is_political_article"]), data
