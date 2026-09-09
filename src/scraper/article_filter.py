"""LLM filter — clasifica un texto en 5 categorías editoriales.

El proveedor concreto lo decide `ProviderChain` (Gemini, Claude por API,
o el agente vía scripts/agent_filter.py). Categorías:
- "political_article": política COLOMBIANA con impacto institucional (CONSERVAR)
- "political_foreign": política de otro país, cubierta por prensa colombiana
- "nonpolitical_article": artículo bien formado pero sin dimensión política
- "biography_static": perfiles de personas o páginas institucionales estáticas
- "garbage": menús, listas de enlaces, fragmentos sin coherencia

Solo se conservan los textos clasificados como "political_article".

`political_foreign` existe porque el corpus es de prensa colombiana, y los
medios colombianos cubren el mundo: un análisis de las elecciones en Chile
está en un medio colombiano pero no es política colombiana. Las 8 clases
ideológicas están ancladas en actores y discurso de Colombia (V-Party
situado en la agenda nacional), así que etiquetar política extranjera con
esos marcadores no tiene sentido metodológico. Se separa en su propia
categoría, en vez de mezclarla con "nonpolitical", para poder medir cuánto
contenido internacional produce cada fuente.
"""

import json
import logging

from src.scraper.llm_providers import (
    GeminiProvider,
    ProviderChain,
)
from src.scraper.prompts import FILTER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# Categorías válidas (deben coincidir con FILTER_SYSTEM_PROMPT).
FILTER_CATEGORIES: list[str] = [
    "political_article",
    "political_foreign",
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


# El control de cuota y los reintentos viven ahora en ProviderChain
# (src/scraper/llm_providers.py). Antes eran variables globales de este módulo,
# lo que impedía tener dos proveedores con estados de cuota independientes:
# agotar Gemini apagaba también al de relevo.


def _as_chain(client, model: str, escalate_model: str | None) -> ProviderChain:
    """Acepta una cadena ya construida o un cliente suelto de Gemini.

    Los llamadores antiguos (pipeline, scripts/scraper) pasan un
    `genai.Client`; se envuelve al vuelo para no tocarlos.
    """
    if isinstance(client, ProviderChain):
        return client
    return ProviderChain([GeminiProvider(client, model, escalate_model, 0.0)])


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
        escalate_model: Modelo a usar cuando el primario duda (~4x más
            caro pero más preciso). Pasa None para desactivar el escalado.
            Si `client` ya es un ProviderChain, este parámetro solo actúa
            como interruptor: el modelo concreto lo aporta cada proveedor
            (`FilterProvider.escalate_model`), porque el de relevo no tiene
            por qué compartir catálogo con el primario.
        escalate_threshold: Si confidence < este valor, escala al
            escalate_model. Default 0.7.

    Returns:
        Tupla (es_político_artículo, info). `info` incluye:
            - category, confidence, reason: respuesta del LLM
            - escalated (bool): si se usó el modelo escalado
            - primary_confidence (opcional): confianza del modelo primario
              cuando se escala (útil para diagnóstico)
    """
    chain = _as_chain(client, model, escalate_model)
    truncated = text[:max_chars]
    response, provider_name = chain.call(
        FILTER_SYSTEM_PROMPT, truncated, _FILTER_RESPONSE_SCHEMA, 512,
    )
    if response is None:
        return False, None

    data = parse_filter_response(response)
    if data is None:
        return False, None

    data["escalated"] = False
    data["provider"] = provider_name

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
        response_esc, provider_esc = chain.call(
            FILTER_SYSTEM_PROMPT, truncated, _FILTER_RESPONSE_SCHEMA, 512,
            escalated=True,
        )
        if response_esc is not None:
            data_esc = parse_filter_response(response_esc)
            if data_esc is not None:
                data = data_esc
                data["escalated"] = True
                data["primary_confidence"] = primary_conf
                data["provider"] = provider_esc

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
