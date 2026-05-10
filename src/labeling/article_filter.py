"""LLM filter — decide si un texto es un artículo de noticia real o basura.

Usa Gemini para clasificar cada texto en 5 categorías:
- "article": artículo de noticia bien formado (CONSERVAR)
- "garbage": menú, lista de URLs, sitemap, glosario, formulario
- "biography": biografía o página "acerca de"
- "static_page": página institucional sin valor noticioso
- "other": cualquier otra cosa que no sea un artículo

Solo se conservan los textos clasificados como "article".
"""

import json
import logging
import time

logger = logging.getLogger(__name__)

FILTER_SYSTEM_PROMPT = """Eres un validador de contenido. Tu tarea es decidir si un texto es un artículo de noticia colombiano bien formado, o si es basura/contenido no editorial.

## CATEGORÍAS

- **article**: Artículo de noticia/opinión real, con párrafos coherentes y contenido editorial.
- **garbage**: Menús de navegación, listas de URLs, sitemaps en bruto, glosarios, listados de documentos, formularios, contenido repetitivo sin coherencia narrativa.
- **biography**: Biografía o perfil de una persona, página "Acerca de", "Quiénes somos".
- **static_page**: Página institucional estática (estructura organizativa, misión y visión, equipos, contáctenos).
- **other**: Cualquier otro contenido que NO sea un artículo de noticia (recetas, horóscopo, programación TV, listados deportivos sin análisis, etc.).

## REGLAS

1. Si el texto tiene párrafos coherentes con narrativa periodística → "article"
2. Si el texto es una sucesión de títulos, fechas y URLs → "garbage"
3. Si describe la trayectoria de una persona como sujeto principal → "biography"
4. Si parece un menú, glosario o lista de documentos → "garbage"
5. En caso de duda entre "article" y "garbage" → escoge "garbage"

## FORMATO DE RESPUESTA (solo JSON, nada más)

```json
{"is_article": true, "category": "article", "reason": "Artículo de noticia política sobre X"}
```

o

```json
{"is_article": false, "category": "garbage", "reason": "Lista de URLs sin texto editorial"}
```
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
    except json.JSONDecodeError:
        logger.warning("No se pudo parsear filter response: %s", text[:200])
        return None

    if "is_article" not in data or "category" not in data:
        return None

    return data


def call_filter_with_retry(
    client,
    model: str,
    text: str,
    max_retries: int = 3,
) -> str | None:
    """Llama al LLM filter con retry y backoff exponencial."""
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config={
                    "system_instruction": FILTER_SYSTEM_PROMPT,
                    "max_output_tokens": 200,
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
    """Pregunta al LLM si el texto es un artículo de noticia real.

    Args:
        client: Cliente de Google GenAI.
        text: Texto del artículo.
        model: Modelo de Gemini a usar.
        max_chars: Caracteres iniciales del texto a enviar al LLM
            (suficiente para clasificar sin gastar tokens innecesarios).

    Returns:
        Tupla (es_artículo, info) donde info es el JSON parseado del LLM
        con campos is_article, category, reason.
    """
    truncated = text[:max_chars]
    response = call_filter_with_retry(client, model, truncated)
    if response is None:
        return False, None

    data = parse_filter_response(response)
    if data is None:
        return False, None

    return bool(data["is_article"]), data
