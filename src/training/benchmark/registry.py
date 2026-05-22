"""Registro de encoders disponibles para el benchmark.

Cada entrada apunta a un config en `configs/model/<alias>.yaml`.
Para añadir un nuevo encoder al benchmark:
1. Crear `configs/model/<alias>.yaml`
2. Añadir el alias a `MODEL_REGISTRY` aquí
"""

# alias → identificador HuggingFace (informativo, la fuente de verdad
# es el config Hydra correspondiente en configs/model/<alias>.yaml)
MODEL_REGISTRY: dict[str, str] = {
    "confliberto": "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
    "maria": "PlanTL-GOB-ES/roberta-base-bne",
    "beto": "dccuchile/bert-base-spanish-wwm-cased",
    # Para añadir más:
    # "xlmr": "FacebookAI/xlm-roberta-base",
    # "robertuito": "pysentimiento/robertuito-base-uncased",
}

AVAILABLE_MODELS: list[str] = list(MODEL_REGISTRY.keys())
