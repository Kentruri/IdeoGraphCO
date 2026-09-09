"""Proveedores de LLM intercambiables para el filtro, con relevo automático.

El filtro no depende de un proveedor concreto: recibe una CADENA ordenada de
proveedores y usa el primero que tenga cuota. Cuando el activo se queda sin
créditos, el siguiente toma el relevo sin perder el artículo en curso y sin
reiniciar el proceso.

    cadena = build_provider_chain(["gemini", "claude"])   # Gemini y, si se
                                                          # agota, Claude

Ambos devuelven el MISMO JSON (`_FILTER_RESPONSE_SCHEMA` de article_filter):
Gemini con `response_schema`, Claude con una herramienta forzada cuyo
`input_schema` es ese mismo esquema. Así la salida no depende de que el
modelo "se porte bien" con el formato en ninguno de los dos casos.

**Advertencia metodológica**: dos modelos distintos aplican el codebook con
criterios ligeramente distintos. Si el corpus se filtra a medias con cada uno,
su composición mezcla dos fronteras de decisión. Por eso cada decisión queda
registrada con el `provider` que la tomó en `logs/filter_decisions.jsonl`:
permite medir la concordancia entre ambos sobre una muestra solapada y
reportarla, en vez de asumir que son equivalentes.
"""

from __future__ import annotations

import json
import logging
import threading
import time

logger = logging.getLogger(__name__)


class QuotaExhausted(RuntimeError):
    """Sin créditos o rate limit sostenido: toca relevar al proveedor."""


class TransientError(RuntimeError):
    """Fallo pasajero (red, 5xx, sobrecarga): se reintenta con el mismo."""


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------

class FilterProvider:
    """Interfaz común: texto + esquema → JSON como string.

    `min_interval` es la espera recomendada entre llamadas para respetar el
    límite por minuto del plan. El llamador la consulta en vez de tener un
    valor fijo: al relevar, el ritmo se ajusta solo al proveedor nuevo.
    """

    name = "?"

    def __init__(self, client, model: str, escalate_model: str | None,
                 min_interval: float):
        self.client = client
        self.model = model
        self.escalate_model = escalate_model
        self.min_interval = min_interval

    def model_for(self, escalated: bool) -> str:
        return (self.escalate_model or self.model) if escalated else self.model

    def complete(self, system: str, user: str, schema: dict,
                 max_tokens: int, escalated: bool = False) -> str:
        raise NotImplementedError


class GeminiProvider(FilterProvider):
    name = "gemini"

    def complete(self, system, user, schema, max_tokens, escalated=False):
        try:
            response = self.client.models.generate_content(
                model=self.model_for(escalated),
                contents=user,
                config={
                    "system_instruction": system,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                    # Sin cadena de pensamiento: la tarea es clasificación
                    # corta y el CoT solo añade latencia y tokens.
                    "thinking_config": {"thinking_budget": 0},
                    "max_output_tokens": max_tokens,
                    "temperature": 0.0,
                },
            )
        except Exception as exc:
            raise _classify_error(exc) from exc
        return response.text


# El esquema JSON del filtro usa `minimum`/`maximum` en `confidence`; la API de
# herramientas de Anthropic acepta JSON Schema estándar e ignora lo que no
# aplica, así que se reusa tal cual y no hay dos esquemas que mantener.
_CLAUDE_TOOL_NAME = "clasificar_articulo"


class ClaudeProvider(FilterProvider):
    """Claude vía API de Anthropic, con salida forzada por herramienta.

    El prompt del sistema del filtro son ~2.600 tokens que se repiten
    IDÉNTICOS en las 50.000 llamadas. Marcarlo con `cache_control` hace que
    a partir de la segunda llamada se cobre como lectura de caché (una
    fracción del precio normal): sin esto, el prompt del sistema domina la
    factura entera.
    """

    name = "claude"

    def complete(self, system, user, schema, max_tokens, escalated=False):
        try:
            response = self.client.messages.create(
                model=self.model_for(escalated),
                max_tokens=max_tokens,
                temperature=0.0,
                system=[{
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=[{
                    "name": _CLAUDE_TOOL_NAME,
                    "description": (
                        "Registra la clasificación editorial del texto según "
                        "las reglas del sistema."
                    ),
                    "input_schema": schema,
                }],
                # Herramienta forzada: la respuesta ES el objeto del esquema,
                # nunca prosa ni JSON envuelto en markdown.
                tool_choice={"type": "tool", "name": _CLAUDE_TOOL_NAME},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:
            raise _classify_error(exc) from exc

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return json.dumps(block.input, ensure_ascii=False)
        raise TransientError("Claude no devolvió el bloque tool_use esperado")


# Señales de agotamiento de cuota/créditos. Lo demás se trata como pasajero:
# equivocarse hacia "pasajero" solo cuesta un reintento, mientras que dar por
# agotado un proveedor sano lo saca de la cadena para el resto de la corrida.
_QUOTA_MARKERS = (
    "quota", "resource_exhausted", "insufficient_quota",
    "credit balance", "billing", "payment required",
)
_TRANSIENT_MARKERS = ("overloaded", "503", "502", "504", "529", "timeout")


def _classify_error(exc: Exception) -> Exception:
    msg = str(exc).lower()
    if any(marker in msg for marker in _TRANSIENT_MARKERS):
        return TransientError(str(exc))
    if any(marker in msg for marker in _QUOTA_MARKERS):
        return QuotaExhausted(str(exc))
    if "429" in msg or "rate limit" in msg or "rate_limit" in msg:
        # Un 429 aislado es el límite POR MINUTO (pasajero); solo una racha
        # sostenida significa cuota agotada. Esa distinción la hace la cadena
        # contando 429 consecutivos, no este clasificador.
        return TransientError(str(exc))
    return TransientError(str(exc))


# ---------------------------------------------------------------------------
# Cadena con relevo
# ---------------------------------------------------------------------------

class ProviderChain:
    """Usa el primer proveedor con cuota; al agotarse, releva al siguiente.

    El relevo es PERMANENTE dentro de la corrida: una vez que un proveedor se
    marca agotado no se reintenta, porque volver a probarlo cada artículo
    gastaría el mismo tiempo muerto que motivó el relevo. Al relanzar el
    script la cadena arranca limpia.
    """

    def __init__(self, providers: list[FilterProvider], quota_streak: int = 5,
                 max_retries: int = 3):
        if not providers:
            raise ValueError("La cadena necesita al menos un proveedor")
        self._providers = providers
        self._quota_streak = quota_streak
        self._max_retries = max_retries
        self._lock = threading.Lock()
        self._exhausted: set[str] = set()
        self._rate_streak: dict[str, int] = {}

    @property
    def providers(self) -> list[FilterProvider]:
        return list(self._providers)

    def active(self) -> FilterProvider | None:
        with self._lock:
            for provider in self._providers:
                if provider.name not in self._exhausted:
                    return provider
        return None

    def min_interval(self) -> float:
        provider = self.active()
        return provider.min_interval if provider else 0.0

    def exhausted(self) -> list[str]:
        with self._lock:
            return sorted(self._exhausted)

    def _mark_exhausted(self, provider: FilterProvider, reason: str) -> None:
        with self._lock:
            if provider.name in self._exhausted:
                return
            self._exhausted.add(provider.name)
            remaining = [p.name for p in self._providers
                         if p.name not in self._exhausted]
        logger.error(
            "Proveedor '%s' agotado (%s). %s",
            provider.name, reason,
            f"Releva: {remaining[0]}." if remaining
            else "No quedan proveedores de relevo.",
        )

    def call(self, system: str, user: str, schema: dict, max_tokens: int,
             escalated: bool = False) -> tuple[str | None, str | None]:
        """Devuelve (json_string, nombre_del_proveedor). (None, None) si falla."""
        while True:
            provider = self.active()
            if provider is None:
                return None, None
            text = self._call_one(provider, system, user, schema,
                                  max_tokens, escalated)
            if text is not None:
                return text, provider.name
            # `_call_one` devuelve None solo tras marcar el proveedor agotado
            # o tras quemar los reintentos; en el primer caso el bucle pasa al
            # siguiente, en el segundo `active()` sigue igual y saldríamos en
            # bucle infinito — por eso se comprueba explícitamente.
            if provider.name not in self._exhausted:
                return None, provider.name

    def _call_one(self, provider, system, user, schema, max_tokens, escalated):
        for attempt in range(self._max_retries):
            try:
                text = provider.complete(system, user, schema, max_tokens,
                                         escalated)
            except QuotaExhausted as exc:
                self._mark_exhausted(provider, str(exc)[:120])
                return None
            except TransientError as exc:
                msg = str(exc).lower()
                is_rate = "429" in msg or "rate" in msg
                if is_rate:
                    with self._lock:
                        streak = self._rate_streak.get(provider.name, 0) + 1
                        self._rate_streak[provider.name] = streak
                    if streak >= self._quota_streak:
                        self._mark_exhausted(
                            provider, f"{streak} rate limits seguidos")
                        return None
                    wait = 60.0
                else:
                    wait = 2.0 ** (attempt + 1)
                logger.warning("[%s] intento %d/%d: %s. Espera %.0fs",
                               provider.name, attempt + 1, self._max_retries,
                               str(exc)[:120], wait)
                if attempt < self._max_retries - 1:
                    time.sleep(wait)
                continue
            with self._lock:
                self._rate_streak[provider.name] = 0
            return text
        return None


# ---------------------------------------------------------------------------
# Construcción desde el entorno
# ---------------------------------------------------------------------------

# Ritmos por defecto. Gemini: 4.5s ≈ plan gratuito (~13 RPM). Claude: el plan
# de pago permite mucho más, así que la espera es simbólica.
_DEFAULTS = {
    "gemini": {
        "env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash-lite",
        "escalate": "gemini-2.5-flash",
        "interval": 4.5,
    },
    "claude": {
        "env": "ANTHROPIC_API_KEY",
        "model": "claude-haiku-4-5-20251001",
        "escalate": "claude-sonnet-5",
        "interval": 0.2,
    },
}


def available_providers() -> list[str]:
    import os
    return [name for name, spec in _DEFAULTS.items()
            if os.environ.get(spec["env"])]


def build_provider_chain(
    order: list[str],
    models: dict[str, str] | None = None,
    escalate_models: dict[str, str] | None = None,
    intervals: dict[str, float] | None = None,
    strict: bool = False,
) -> ProviderChain:
    """Construye la cadena en el orden pedido, saltando los que no tengan clave.

    Con `strict=False` (por defecto) pedir "gemini,claude" sin
    ANTHROPIC_API_KEY produce una cadena de solo Gemini y un aviso: el relevo
    es opcional, no debería impedir arrancar.
    """
    import os

    models = models or {}
    escalate_models = escalate_models or {}
    intervals = intervals or {}

    built: list[FilterProvider] = []
    for name in order:
        spec = _DEFAULTS.get(name)
        if spec is None:
            raise ValueError(
                f"Proveedor desconocido: '{name}'. "
                f"Disponibles: {', '.join(_DEFAULTS)}"
            )
        api_key = os.environ.get(spec["env"])
        if not api_key:
            message = f"Falta {spec['env']}: el proveedor '{name}' queda fuera."
            if strict:
                raise SystemExit(f"✗ {message}")
            logger.warning(message)
            continue

        model = models.get(name, spec["model"])
        escalate = escalate_models.get(name, spec["escalate"])
        interval = intervals.get(name, spec["interval"])

        if name == "gemini":
            from google import genai
            built.append(GeminiProvider(
                genai.Client(api_key=api_key), model, escalate, interval))
        else:
            try:
                import anthropic
            except ModuleNotFoundError as exc:
                raise SystemExit(
                    "✗ Falta el paquete 'anthropic'. Instálalo con:\n"
                    "    .venv/bin/pip install anthropic"
                ) from exc
            built.append(ClaudeProvider(
                anthropic.Anthropic(api_key=api_key), model, escalate,
                interval))

    if not built:
        envs = " o ".join(spec["env"] for spec in _DEFAULTS.values())
        raise SystemExit(
            f"✗ Ningún proveedor utilizable. Define {envs} en .env"
        )
    return ProviderChain(built)
