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
import threading
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
# Problemas de LIMPIEZA del texto, independientes de la categoría. Los tres
# "bloqueantes" descartan el artículo aunque sea político; `boilerplate_residual`
# solo se registra y alimenta la mejora del cleaner (scripts/analyze_filter_log).
TEXT_ISSUES: list[str] = [
    "boilerplate_residual",
    "digest_multinoticia",
    "truncado",
    "preview_paywall",
]
BLOCKING_TEXT_ISSUES: frozenset[str] = frozenset({
    "digest_multinoticia",   # varias ideologías en un documento single-label
    "truncado",
    "preview_paywall",
})

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
        "text_issues": {
            "type": "array",
            "items": {"type": "string", "enum": TEXT_ISSUES},
        },
    },
    "required": ["category", "confidence", "reason", "text_issues"],
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


# Circuit breaker de cuota: tras N errores de cuota consecutivos se asume
# agotamiento (429 sostenido / cuota diaria) y las llamadas siguientes fallan
# rápido en vez de quemar ~180s en sleeps por URL. Los artículos afectados
# quedan como filter_error (transitorio) y se reintentan en la próxima
# corrida. Cualquier llamada exitosa re-arma el breaker.
_QUOTA_LOCK = threading.Lock()
_QUOTA_CONSECUTIVE = 0
_QUOTA_BREAKER_THRESHOLD = 5
_QUOTA_TRIPPED_LOGGED = False


def _quota_breaker_tripped() -> bool:
    with _QUOTA_LOCK:
        return _QUOTA_CONSECUTIVE >= _QUOTA_BREAKER_THRESHOLD


def _record_quota_error() -> None:
    global _QUOTA_CONSECUTIVE, _QUOTA_TRIPPED_LOGGED
    with _QUOTA_LOCK:
        _QUOTA_CONSECUTIVE += 1
        if _QUOTA_CONSECUTIVE >= _QUOTA_BREAKER_THRESHOLD and not _QUOTA_TRIPPED_LOGGED:
            _QUOTA_TRIPPED_LOGGED = True
            logger.error(
                "Cuota del LLM agotada (%d errores de cuota consecutivos): el "
                "resto de la corrida fallará rápido como filter_error y se "
                "reintentará en la próxima corrida.", _QUOTA_CONSECUTIVE,
            )


def _record_llm_success() -> None:
    global _QUOTA_CONSECUTIVE, _QUOTA_TRIPPED_LOGGED
    with _QUOTA_LOCK:
        _QUOTA_CONSECUTIVE = 0
        _QUOTA_TRIPPED_LOGGED = False


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
    if _quota_breaker_tripped():
        return None
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
            _record_llm_success()
            return response.text
        except Exception as e:
            error_msg = str(e)
            is_quota = "429" in error_msg or "quota" in error_msg.lower()
            if is_quota:
                _record_quota_error()
                if _quota_breaker_tripped():
                    return None
                wait = 60
                logger.warning("Rate limit. Esperando %ds...", wait)
            else:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Error filter intento %d/%d: %s. Esperando %ds...",
                    attempt + 1, max_retries, error_msg[:100], wait,
                )
            if attempt < max_retries - 1:
                # Dormir solo si queda otro intento: el sleep tras el último
                # era tiempo muerto puro.
                time.sleep(wait)
    return None


def is_real_article(
    client,
    text: str,
    model: str = "gemini-2.5-flash-lite",
    max_chars: int = 3000,
    escalate_model: str | None = "gemini-2.5-flash",
    escalate_threshold: float = 0.7,
    rate_limiter=None,
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
        # La llamada escalada también cuenta contra el RPM global: sin esta
        # espera, rachas de baja confianza duplicaban el ritmo efectivo.
        if rate_limiter is not None:
            rate_limiter.wait()
        response_esc = call_filter_with_retry(client, escalate_model, truncated)
        if response_esc is not None:
            data_esc = parse_filter_response(response_esc)
            if data_esc is not None:
                data = data_esc
                data["escalated"] = True
                data["primary_confidence"] = primary_conf

    # Normalizar text_issues y aplicar los bloqueantes: un digest con varias
    # noticias, un preview de paywall o un texto truncado no sirven como
    # documento single-label aunque su contenido sea político.
    issues = [i for i in (data.get("text_issues") or []) if i in TEXT_ISSUES]
    data["text_issues"] = issues
    blocking = sorted(set(issues) & BLOCKING_TEXT_ISSUES)
    if blocking:
        data["blocked_by"] = blocking
        data["category"] = "garbage"
        data["reason"] = f"descartado por {', '.join(blocking)}"
        return False, data

    is_political = data.get("category") == "political_article"
    return is_political, data
