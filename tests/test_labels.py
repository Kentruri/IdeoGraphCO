"""Tests de resolución de etiquetas (src/training/data/dataset.py)."""

import pytest

from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES
from src.training.data.dataset import legacy_argmax_is_tie, resolve_label_idx


def test_label_idx_has_priority():
    assert resolve_label_idx({"label_idx": 3, "label": "populismo"}) == 3


def test_label_string_resolves():
    assert resolve_label_idx({"label": "populismo"}) == CLASS_TO_IDX["populismo"]


def test_legacy_scores_argmax():
    article = {cls: 0.1 for cls in IDEOLOGY_CLASSES}
    article["soberanismo"] = 0.9
    assert resolve_label_idx(article) == CLASS_TO_IDX["soberanismo"]


def test_invalid_label_raises():
    with pytest.raises(ValueError):
        resolve_label_idx({"label": "neutral"})
    with pytest.raises(ValueError):
        resolve_label_idx({"label_idx": 8})
    with pytest.raises(ValueError):
        resolve_label_idx({"titulo": "sin etiquetas"})


def test_tie_detection_legacy_only():
    tied = {cls: 0.0 for cls in IDEOLOGY_CLASSES}
    tied["populismo"] = 0.7
    tied["personalismo"] = 0.7
    assert legacy_argmax_is_tie(tied) is True

    untied = dict(tied, populismo=0.8)
    assert legacy_argmax_is_tie(untied) is False

    # Con etiqueta explícita nunca hay empate
    assert legacy_argmax_is_tie({**tied, "label": "populismo"}) is False


def test_inference_chunking_matches_training():
    """El predictor debe trocear IGUAL que el dataset de entrenamiento.

    Antes `max_chunks` estaba hardcodeado en 8 en el predictor mientras el
    entrenamiento usaba 16: el modelo veía hasta el token 6.270 al entrenar y
    solo 3.198 al servir (train/serve skew, peor en artículos largos).
    """
    import json
    import tempfile
    from pathlib import Path

    import yaml

    from src.core.paths import CONFIGS_DIR
    from src.inference.predictor import _training_chunking_defaults
    from src.training.data.dataset import IdeoGraphDataset

    trained = _training_chunking_defaults()
    cfg = yaml.safe_load((CONFIGS_DIR / "data" / "default.yaml").read_text(encoding="utf-8"))

    # 1) El predictor lee EXACTAMENTE lo que usa el entrenamiento.
    for key in ("chunk_size", "chunk_stride", "max_chunks"):
        assert trained[key] == cfg[key], f"{key}: {trained[key]} != {cfg[key]}"

    # 2) Paridad de troceo sobre el mismo texto, con la misma config.
    model_name = "dccuchile/bert-base-spanish-wwm-cased"
    texto = "El Congreso aprobó la reforma pensional en segundo debate. " * 200
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "a.jsonl"
        path.write_text(
            json.dumps({"id": "x", "text": texto, "label": "populismo"}) + "\n",
            encoding="utf-8",
        )
        ds = IdeoGraphDataset(
            path, model_name=model_name,
            chunk_size=trained["chunk_size"],
            chunk_stride=trained["chunk_stride"],
            max_chunks=trained["max_chunks"],
        )
        k_dataset = ds[0]["input_ids"].shape[0]

        # Misma lógica que IdeoClassifierPredictor._chunk_and_pad
        ids = ds.tokenizer(texto, add_special_tokens=False)["input_ids"]
        content = trained["chunk_size"] - 2
        k_pred, start_pos = 0, 0
        while start_pos < len(ids) and k_pred < trained["max_chunks"]:
            end_pos = min(start_pos + content, len(ids))
            k_pred += 1
            if end_pos == len(ids):
                break
            start_pos += trained["chunk_stride"]

    assert k_dataset == k_pred, f"dataset={k_dataset} chunks, predictor={k_pred}"


def test_xlnet_places_cls_at_end():
    """XLNet lleva <cls> al final; dataset y predictor deben coincidir."""
    from transformers import AutoTokenizer

    for name, esperado_al_final in (
        ("xlnet-base-cased", True),
        ("dccuchile/bert-base-spanish-wwm-cased", False),
    ):
        tok = AutoTokenizer.from_pretrained(name)
        detectado = "xlnet" in type(tok).__name__.lower()
        assert detectado is esperado_al_final, name
