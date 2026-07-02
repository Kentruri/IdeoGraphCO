"""Registro de encoders disponibles para el benchmark del clasificador.

Los 4 encoders requeridos por el anteproyecto (OE2):
BETO, XLNet, XLM-RoBERTa, ConfliBERT-Spanish.

Cada alias apunta a un config en `configs/model/<alias>.yaml`. Para añadir
otro encoder:
    1. Crear `configs/model/<alias>.yaml`
    2. Añadir el alias a `MODEL_REGISTRY` aquí
"""

# alias → identificador HuggingFace (informativo — la fuente de verdad es el
# config Hydra en configs/model/<alias>.yaml).
#
# TBD (docs/preguntas-director.md tema 4): "xlnet" apunta a mDeBERTa porque
# XLNet no tiene versión oficial en español. Ajustar tras la decisión del
# director.
MODEL_REGISTRY: dict[str, str] = {
    "confliberto": "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
    "beto": "dccuchile/bert-base-spanish-wwm-cased",
    "xlm-roberta": "FacebookAI/xlm-roberta-base",
    "xlnet": "microsoft/mdeberta-v3-base",  # TBD, placeholder
}

AVAILABLE_MODELS: list[str] = list(MODEL_REGISTRY.keys())
