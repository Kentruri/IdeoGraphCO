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
# "xlnet" usa el XLNet original (inglés): no existe versión oficial en español
# y se decidió (ago-2026) mantener el modelo comprometido en el anteproyecto.
# Su desempeño esperado sobre texto en español es bajo; ese resultado es parte
# del hallazgo del benchmark, no un error.
MODEL_REGISTRY: dict[str, str] = {
    "confliberto": "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
    "beto": "dccuchile/bert-base-spanish-wwm-cased",
    "xlm-roberta": "FacebookAI/xlm-roberta-base",
    "xlnet": "xlnet-base-cased",
}

AVAILABLE_MODELS: list[str] = list(MODEL_REGISTRY.keys())

# Encoders FUERA del anteproyecto, como experimento adicional: no corren por
# defecto, hay que pedirlos con --models. "mrbert-es" (BSC-LT, feb-2026) es un
# ModernBERT español de 8.192 tokens: lee el artículo entero sin trocear, para
# medir si la dilución del mean-pool (limitación declarada) cuesta acierto.
EXTRA_MODELS: dict[str, str] = {
    "mrbert-es": "BSC-LT/MrBERT-es",
}

ALL_MODELS: list[str] = AVAILABLE_MODELS + list(EXTRA_MODELS)
