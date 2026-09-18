"""Jueces intercambiables para el silver: cada uno emite un Veredicto.

Un juez envuelve un proveedor de LLM (los mismos de `src.scraper.llm_providers`)
con el codebook como prompt de sistema y devuelve, por artículo, la clase
dominante y los 8 scores. El ensemble (`ensemble.py`) hace que varios jueces
vean el MISMO artículo y `consensus.py` decide qué hacer con sus veredictos.

Por qué jueces de familias distintas
-----------------------------------
El acuerdo entre dos copias del mismo modelo mide la consistencia del modelo,
no la corrección de la etiqueta: sus errores están correlacionados y coinciden
también cuando se equivocan. El acuerdo solo es evidencia si los jueces fallan
de forma distinta, y eso exige familias distintas (Gemini + Claude). Por eso
`build_judges` avisa cuando todos los jueces comparten familia.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.silver.judge import (
    _LABEL_RESPONSE_SCHEMA,
    AXIS_NAMES,
    DOMINANT_KEY,
    JUDGE_MAX_CHARS,
    normalize_labels,
    parse_response,
)
from src.core.text import build_model_input
from src.scraper.llm_providers import (
    ClaudeProvider,
    FilterProvider,
    GeminiProvider,
    QuotaExhausted,
    TransientError,
)

logger = logging.getLogger(__name__)


# Catálogo de jueces disponibles. `family` es lo que importa para la
# heterogeneidad; `interval` es la espera entre llamadas del plan más
# restrictivo de cada proveedor.
JUDGE_REGISTRY: dict[str, dict] = {
    "gemini": {
        "family": "gemini", "model": "gemini-2.5-flash",
        "env": "GEMINI_API_KEY", "interval": 4.5,
    },
    "gemini-lite": {
        "family": "gemini", "model": "gemini-2.5-flash-lite",
        "env": "GEMINI_API_KEY", "interval": 4.5,
    },
    "claude": {
        "family": "claude", "model": "claude-haiku-4-5-20251001",
        "env": "ANTHROPIC_API_KEY", "interval": 0.2,
    },
    "claude-sonnet": {
        "family": "claude", "model": "claude-sonnet-5",
        "env": "ANTHROPIC_API_KEY", "interval": 0.2,
    },
}

# Bloque de formato que se añade a cualquier codebook externo. El esquema JSON
# del proveedor ya fuerza la estructura, pero el modelo tiene que saber qué
# significa cada campo; sin esto, un codebook escrito para humanos no dice
# nada de scores en [0, 1] ni de "dominant".
OUTPUT_FORMAT_BLOCK = """

## FORMATO DE RESPUESTA (solo JSON, nada más)

Devuelve un objeto con 8 campos numéricos DIRECTAMENTE en [0.0, 1.0] — uno por
clase, con la intensidad con que el texto la expresa (0.00 ausente, 0.50
moderado, 1.00 dominante) — y el campo "dominant" con UNA de las ocho clases:
la que estructura el argumento del texto.

{
""" + ",\n".join(f'    "{axis}": 0.0' for axis in AXIS_NAMES) + f""",
    "{DOMINANT_KEY}": "{AXIS_NAMES[0]}"
}}
"""


def system_prompt_from(codebook_path: str | Path | None) -> str:
    """Prompt de sistema del juez.

    Sin ruta, usa el codebook del proyecto (`codebook.build_system_prompt`).
    Con ruta, usa ese archivo tal cual — es como se enchufa el codebook de
    un anotador externo — y le añade el bloque de formato si no lo trae.
    """
    if codebook_path is None:
        from src.agents.silver.codebook import build_system_prompt

        return build_system_prompt(include_examples=True)

    text = Path(codebook_path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"El codebook está vacío: {codebook_path}")
    if f'"{DOMINANT_KEY}"' not in text:
        text += OUTPUT_FORMAT_BLOCK
    return text


@dataclass
class Verdict:
    """Lo que un juez dice de un artículo. `ok=False` = no hubo veredicto."""

    judge: str
    model: str
    family: str
    dominant: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    ok: bool = False
    error: str | None = None
    quota: bool = False          # el fallo fue de cuota: el juez debe retirarse
    truncated: bool = False      # el juez vio el texto recortado

    def to_dict(self) -> dict:
        return {
            "judge": self.judge, "model": self.model, "family": self.family,
            "dominant": self.dominant, "scores": self.scores, "ok": self.ok,
            "error": self.error, "truncated": self.truncated,
        }


class Judge:
    """Un proveedor + el codebook. Thread-safe: cada juez espacia sus llamadas."""

    def __init__(self, name: str, provider: FilterProvider, system_prompt: str,
                 family: str, max_chars: int = JUDGE_MAX_CHARS,
                 max_retries: int = 3):
        self.name = name
        self.provider = provider
        self.system_prompt = system_prompt
        self.family = family
        self.max_chars = max_chars
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._last_call = 0.0

    @property
    def model(self) -> str:
        return self.provider.model

    def _pace(self) -> None:
        """Respeta el intervalo mínimo del proveedor entre llamadas."""
        with self._lock:
            wait = self.provider.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def judge(self, title: str | None, text: str) -> Verdict:
        model_input = build_model_input(title, text)
        truncated = len(model_input) > self.max_chars
        user = model_input[: self.max_chars]
        verdict = Verdict(judge=self.name, model=self.model, family=self.family,
                          truncated=truncated)

        for attempt in range(self.max_retries):
            self._pace()
            try:
                raw = self.provider.complete(
                    self.system_prompt, user, _LABEL_RESPONSE_SCHEMA, 2048,
                )
            except QuotaExhausted as exc:
                verdict.error = f"cuota: {str(exc)[:120]}"
                verdict.quota = True
                return verdict
            except TransientError as exc:
                verdict.error = f"transitorio: {str(exc)[:120]}"
                # Un 429 aislado es límite por minuto: esperar un poco más que
                # el intervalo normal antes de reintentar.
                time.sleep(min(60.0, 2.0 ** (attempt + 2)))
                continue

            data = parse_response(raw)
            if data is None:
                verdict.error = "respuesta inválida (sin JSON válido o sin dominante)"
                continue

            verdict.dominant = data[DOMINANT_KEY]
            verdict.scores = normalize_labels(data)
            verdict.ok = True
            verdict.error = None
            return verdict

        return verdict


def available_judges() -> list[str]:
    """Nombres del catálogo cuya clave de API está en el entorno."""
    return [name for name, spec in JUDGE_REGISTRY.items()
            if os.environ.get(spec["env"])]


def families(judges: list[Judge]) -> set[str]:
    return {j.family for j in judges}


def build_judges(
    names: list[str],
    system_prompt: str,
    models: dict[str, str] | None = None,
) -> list[Judge]:
    """Construye los jueces pedidos. Es ESTRICTO: si falta una clave, falla.

    A diferencia de la cadena del filtro (donde un proveedor ausente solo
    quita el relevo), aquí un juez que falta en silencio cambia el ensemble
    entero — dos jueces en vez de tres, o uno solo — y con él el significado
    de "consenso". Mejor no arrancar.
    """
    if not names:
        raise ValueError("Hay que pedir al menos un juez")
    models = models or {}
    judges: list[Judge] = []
    for name in names:
        spec = JUDGE_REGISTRY.get(name)
        if spec is None:
            raise ValueError(
                f"Juez desconocido: '{name}'. Disponibles: {', '.join(JUDGE_REGISTRY)}")
        api_key = os.environ.get(spec["env"])
        if not api_key:
            raise SystemExit(
                f"✗ Falta {spec['env']} para el juez '{name}'. Añádela a .env "
                f"o pide otros jueces (con clave ahora: "
                f"{', '.join(available_judges()) or 'ninguno'})."
            )
        model = models.get(name, spec["model"])
        if spec["family"] == "gemini":
            from google import genai

            provider = GeminiProvider(genai.Client(api_key=api_key), model,
                                      None, spec["interval"])
        else:
            try:
                import anthropic
            except ModuleNotFoundError as exc:
                raise SystemExit(
                    "✗ Falta el paquete 'anthropic':  .venv/bin/pip install anthropic"
                ) from exc
            provider = ClaudeProvider(anthropic.Anthropic(api_key=api_key), model,
                                      None, spec["interval"])
        judges.append(Judge(name, provider, system_prompt, spec["family"]))

    if len(judges) > 1 and len(families(judges)) == 1:
        logger.warning(
            "Todos los jueces son de la familia '%s': su acuerdo mide la "
            "consistencia del modelo, no la corrección de la etiqueta (errores "
            "correlacionados). Mezcla familias: p. ej. gemini,claude.",
            judges[0].family,
        )
    return judges
