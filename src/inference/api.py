"""Servicio de inferencia HTTP — expone el clasificador para IdeoGraphCO-BE.

Contrato (el que consume el ClassifierClient del backend):

    POST /classify   {"title": str, "text": str}
        → {"label": str, "probabilities": {clase: float ×8}, "model_version": str}
    POST /delta      {"p": {clase: float ×8}, "q": {...}, "method": "jensen_shannon"}
        → {"delta_d": float, "method": str}
    GET  /health     → {"status": "ok", "model_version": str}

Las probabilidades se devuelven en [0, 1] (suman 1), NO en porcentaje.

Uso:
    export IDEOGRAPH_CHECKPOINT=logs/checkpoints/<alias>/best.ckpt
    uvicorn src.inference.api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.core.schema import IDEOLOGY_CLASSES
from src.core.text import build_model_input
from src.inference.delta import delta_d
from src.inference.predictor import IdeoClassifierPredictor

_predictor: IdeoClassifierPredictor | None = None
_model_version: str = "unknown"


class ClassifyRequest(BaseModel):
    title: str = ""
    text: str = Field(min_length=50, description="Cuerpo del artículo (texto plano)")


class ClassifyResponse(BaseModel):
    label: str
    probabilities: dict[str, float]
    model_version: str


class DeltaRequest(BaseModel):
    p: dict[str, float]
    q: dict[str, float]
    method: str = "jensen_shannon"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _predictor, _model_version
    checkpoint = os.environ.get("IDEOGRAPH_CHECKPOINT")
    if not checkpoint or not Path(checkpoint).exists():
        raise RuntimeError(
            "Define IDEOGRAPH_CHECKPOINT con la ruta a un checkpoint válido "
            "(ej. logs/checkpoints/<alias>/best.ckpt)"
        )
    _predictor = IdeoClassifierPredictor(checkpoint)
    _model_version = os.environ.get(
        "IDEOGRAPH_MODEL_VERSION", Path(checkpoint).parent.name,
    )
    yield


app = FastAPI(
    title="IdeoGraphCO — Servicio de inferencia",
    description="Clasificador multiclase de ideología (8 clases) para noticias políticas colombianas.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model_version": _model_version}


@app.post("/classify", response_model=ClassifyResponse)
def classify(request: ClassifyRequest) -> ClassifyResponse:
    if _predictor is None:
        raise HTTPException(status_code=503, detail="Modelo no cargado")
    # Misma composición que el entrenamiento (src/core/text.py): sin esto,
    # el modelo entrenaba sin titular y servía con él.
    text = build_model_input(request.title, request.text)
    result = _predictor.predict(text)
    # El predictor devuelve porcentajes; el contrato del BE usa [0, 1]
    probabilities = {
        cls: round(pct / 100.0, 4)
        for cls, pct in result["probabilities"].items()
    }
    return ClassifyResponse(
        label=result["predicted_class"],
        probabilities=probabilities,
        model_version=_model_version,
    )


@app.post("/delta")
def delta(request: DeltaRequest) -> dict:
    missing = set(IDEOLOGY_CLASSES) - set(request.p) | set(IDEOLOGY_CLASSES) - set(request.q)
    if missing:
        raise HTTPException(status_code=422, detail=f"Faltan clases: {sorted(missing)}")
    try:
        value = delta_d(request.p, request.q, method=request.method)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    return {"delta_d": round(value, 6), "method": request.method}
