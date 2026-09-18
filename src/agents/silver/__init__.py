"""Agentes silver-label — etiquetado automatizado con LLM-as-a-Judge.

Dos caminos:

- `judge.label_news_file`: UN juez (Gemini) por artículo. El original.
- `ensemble.label_with_ensemble`: VARIOS jueces de familias distintas por
  artículo + `consensus.resolve`. El desacuerdo no se descarta: se registra
  con su estado y su grado de acuerdo. `calibration` mide contra el gold si
  ese acuerdo predice el acierto — que es lo que justifica la regla.
"""

from src.agents.silver.codebook import (
    AXIS_DEFINITIONS,
    CALIBRATION_RULES,
    SCALE_LEVELS,
    build_system_prompt,
)
from src.agents.silver.consensus import Consensus, mean_scores, resolve
from src.agents.silver.ensemble import label_with_ensemble
from src.agents.silver.judge import label_news_file, normalize_labels, parse_response
from src.agents.silver.judges import (
    JUDGE_REGISTRY,
    Judge,
    Verdict,
    available_judges,
    build_judges,
    system_prompt_from,
)

__all__ = [
    "AXIS_DEFINITIONS",
    "CALIBRATION_RULES",
    "Consensus",
    "JUDGE_REGISTRY",
    "Judge",
    "SCALE_LEVELS",
    "Verdict",
    "available_judges",
    "build_judges",
    "build_system_prompt",
    "label_news_file",
    "label_with_ensemble",
    "mean_scores",
    "normalize_labels",
    "parse_response",
    "resolve",
    "system_prompt_from",
]
