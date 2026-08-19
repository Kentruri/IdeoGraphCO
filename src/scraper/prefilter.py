"""Pre-filtro local en cascada — reduce la cuota del filter LLM.

Idea (la misma teacher→student de la tesis, aplicada al filtro): las
decisiones acumuladas del filter LLM (`logs/filter_decisions.jsonl`, con
`text_head`) entrenan un clasificador local barato (TF-IDF + regresión
logística) que resuelve los casos obvios sin gastar API:

    p = P(político | texto)
    p <= lo  → DROP directo (obviamente no-político)
    p >= hi  → KEEP directo (obviamente político)
    lo < p < hi → zona gris → decide el LLM (como siempre)

Los umbrales (lo, hi) se calibran en un split de validación al entrenar
(scripts/train_prefilter.py) para mantener precisión alta en ambos extremos.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.core.paths import DATA_DIR

logger = logging.getLogger(__name__)

DEFAULT_PREFILTER_PATH = DATA_DIR / "models" / "prefilter.joblib"


@dataclass
class PrefilterDecision:
    action: str          # "keep" | "drop" | "uncertain"
    probability: float   # P(político)


class PoliticalPrefilter:
    """Clasificador local de politicidad con zona gris delegada al LLM."""

    def __init__(self, pipeline, lo: float, hi: float, meta: dict | None = None):
        self.pipeline = pipeline
        self.lo = lo
        self.hi = hi
        self.meta = meta or {}

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PREFILTER_PATH) -> "PoliticalPrefilter":
        import joblib

        bundle = joblib.load(path)
        return cls(
            pipeline=bundle["pipeline"],
            lo=bundle["lo"],
            hi=bundle["hi"],
            meta=bundle.get("meta", {}),
        )

    def predict_proba(self, text: str) -> float:
        return float(self.pipeline.predict_proba([text])[0][1])

    def decide(self, text: str) -> PrefilterDecision:
        probability = self.predict_proba(text)
        if probability <= self.lo:
            return PrefilterDecision("drop", probability)
        if probability >= self.hi:
            return PrefilterDecision("keep", probability)
        return PrefilterDecision("uncertain", probability)


def try_load_prefilter(path: str | Path | None) -> PoliticalPrefilter | None:
    """Carga el prefilter si existe; None (con log) si no."""
    if path is None:
        return None
    path = Path(path)
    if not path.exists():
        logger.warning(
            "Prefilter no encontrado en %s — el pipeline usará solo el LLM. "
            "Entrénalo con: python scripts/train_prefilter.py", path,
        )
        return None
    prefilter = PoliticalPrefilter.load(path)
    logger.info(
        "Prefilter cargado (%s): lo=%.2f hi=%.2f, entrenado con %s muestras",
        path.name, prefilter.lo, prefilter.hi,
        prefilter.meta.get("n_samples", "?"),
    )
    return prefilter
