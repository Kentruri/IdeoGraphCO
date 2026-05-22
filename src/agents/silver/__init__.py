"""Agentes silver-label — etiquetado automatizado con LLM-as-a-Judge."""

from src.agents.silver.codebook import (
    AXIS_DEFINITIONS,
    CALIBRATION_RULES,
    SCALE_LEVELS,
    build_system_prompt,
)
from src.agents.silver.judge import label_news_file, normalize_labels, parse_response

__all__ = [
    "AXIS_DEFINITIONS",
    "CALIBRATION_RULES",
    "SCALE_LEVELS",
    "build_system_prompt",
    "label_news_file",
    "normalize_labels",
    "parse_response",
]
