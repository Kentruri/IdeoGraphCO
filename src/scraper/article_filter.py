"""LLM filter — clasifica un texto en 4 categorías editoriales.

Usa Gemini para clasificar:
- "political_article": artículo político con impacto institucional (CONSERVAR)
- "nonpolitical_article": artículo bien formado pero sin dimensión política
- "biography_static": perfiles de personas o páginas institucionales estáticas
- "garbage": menús, listas de enlaces, fragmentos sin coherencia

Solo se conservan los textos clasificados como "political_article".
"""

import json
import logging
import time

from src.scraper.prompts import FILTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# Categorías válidas (deben coincidir con FILTER_SYSTEM_PROMPT).
FILTER_CATEGORIES: list[str] = [
    "political_article",
    "nonpolitical_article",
    "biography_static",
    "garbage",
]


# Schema JSON estructurado para Gemini. Cuando se pasa como response_schema,
# el modelo garantiza la presencia de todos los campos y tipos correctos.
# Esto elimina la mayoría de errores de parseo y la necesidad de remover
# wrappers de markdown.
_FILTER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": FILTER_CATEGORIES},
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
        },
        "reason": {"type": "string"},
    },
    "required": ["category", "confidence", "reason"],
}


def parse_filter_response(response_text: str) -> dict | None:
    """Parsea la respuesta del LLM como JSON.

    Con `response_schema` configurado en `call_filter_with_retry`, Gemini
    garantiza un JSON válido con la estructura esperada. Mantenemos try/except
    como red de seguridad por si algo sale mal (paranoia productiva).
    """
    try:
        return json.loads(response_text)
    except json.JSONDecodeError as e:
        logger.warning(
            "No se pudo parsear filter response (%s). Texto: %s",
            e, response_text[:400],
        )
        return None


def call_filter_with_retry(
    client,
    model: str,
    text: str,
    max_retries: int = 3,
) -> str | None:
    """Llama al LLM filter con retry y backoff exponencial.

    Configuración para modelos 2.5 (reasoning):
    - response_mime_type=application/json → JSON sin wrappers de markdown
    - response_schema=_FILTER_RESPONSE_SCHEMA → estructura garantizada
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
                    "response_schema": _FILTER_RESPONSE_SCHEMA,
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
    max_chars: int = 3000,
    escalate_model: str | None = "gemini-2.5-flash",
    escalate_threshold: float = 0.7,
) -> tuple[bool, dict | None]:
    """Pregunta al LLM si el texto es un artículo POLÍTICO real.

    Si la confianza del modelo principal es baja (< escalate_threshold), se
    re-llama automáticamente con un modelo más caro (escalate_model) y se
    usa esa decisión como definitiva. La decisión escalada queda marcada con
    `escalated: true` para análisis posterior.

    Args:
        client: Cliente de Google GenAI.
        text: Texto del artículo.
        model: Modelo primario. Default flash-lite (barato).
        max_chars: Caracteres iniciales del texto a enviar al LLM.
        escalate_model: Modelo a usar cuando el primario duda. Default
            gemini-2.5-flash (~4x más caro pero más preciso). Pasa None
            para desactivar el escalado.
        escalate_threshold: Si confidence < este valor, escala al
            escalate_model. Default 0.7.

    Returns:
        Tupla (es_político_artículo, info). `info` incluye:
            - category, confidence, reason: respuesta del LLM
            - escalated (bool): si se usó el modelo escalado
            - primary_confidence (opcional): confianza del modelo primario
              cuando se escala (útil para diagnóstico)
    """
    truncated = text[:max_chars]
    response = call_filter_with_retry(client, model, truncated)
    if response is None:
        return False, None

    data = parse_filter_response(response)
    if data is None:
        return False, None

    data["escalated"] = False

    # Escalado automático: si el modelo primario duda, re-llamar con el
    # modelo más caro y usar esa respuesta como definitiva.
    conf = data.get("confidence")
    if (
        escalate_model
        and isinstance(conf, (int, float))
        and conf < escalate_threshold
    ):
        primary_conf = conf
        response_esc = call_filter_with_retry(client, escalate_model, truncated)
        if response_esc is not None:
            data_esc = parse_filter_response(response_esc)
            if data_esc is not None:
                data = data_esc
                data["escalated"] = True
                data["primary_confidence"] = primary_conf

    is_political = data.get("category") == "political_article"
    return is_political, data
