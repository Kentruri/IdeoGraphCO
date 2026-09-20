"""Tests de resolución de etiquetas (src/training/data/dataset.py)."""

from pathlib import Path

import pytest

from src.core.paths import ROOT
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


def test_checkpoint_carries_its_own_chunking():
    """El checkpoint tiene que describir su propio troceo.

    La inferencia vive en IdeoGraphCO-BE, que NO tiene
    configs/data/default.yaml. Si el servidor adivina los valores, vuelve el
    train/serve skew que ya ocurrió una vez: se entrenaba con max_chunks=16 y
    se servía con 8, así que el modelo veía hasta el token 6.270 al entrenar y
    3.198 al predecir — peor cuanto más largo el artículo, y sin ningún
    síntoma visible.

    Este test es el contrato con el BE: lea el troceo de los hiperparámetros
    del checkpoint y no de una config que no tiene.
    """
    import yaml

    from src.core.paths import CONFIGS_DIR
    from src.training.models.ideoclassifier import IdeoClassifier

    cfg = yaml.safe_load((CONFIGS_DIR / "data" / "default.yaml").read_text(encoding="utf-8"))
    claves = ("chunk_size", "chunk_stride", "max_chunks")

    model = IdeoClassifier(
        model_name="dccuchile/bert-base-spanish-wwm-cased",
        **{k: cfg[k] for k in claves},
    )
    for k in claves:
        assert k in model.hparams, f"{k} no viaja en el checkpoint"
        assert model.hparams[k] == cfg[k], f"{k}: {model.hparams[k]} != {cfg[k]}"


def test_train_pasa_el_troceo_al_modelo():
    """Sin esto el checkpoint guardaría los valores por defecto, no los usados."""
    fuente = (ROOT / "src" / "training" / "train.py").read_text(encoding="utf-8")
    for k in ("chunk_size", "chunk_stride", "max_chunks"):
        assert f"{k}=cfg.data.{k}" in fuente, f"train.py no pasa {k} al modelo"


def test_chunking_del_dataset_respeta_la_config():
    """El troceo real del dataset coincide con lo que dice la config."""
    import json
    import tempfile

    import yaml

    from src.core.paths import CONFIGS_DIR
    from src.training.data.dataset import IdeoGraphDataset

    cfg = yaml.safe_load((CONFIGS_DIR / "data" / "default.yaml").read_text(encoding="utf-8"))
    texto = "El Congreso aprobó la reforma pensional en segundo debate. " * 200
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "a.jsonl"
        path.write_text(
            json.dumps({"id": "x", "text": texto, "label": "populismo"}) + "\n",
            encoding="utf-8",
        )
        ds = IdeoGraphDataset(
            path, model_name="dccuchile/bert-base-spanish-wwm-cased",
            chunk_size=cfg["chunk_size"], chunk_stride=cfg["chunk_stride"],
            max_chunks=cfg["max_chunks"],
        )
        k_real = ds[0]["input_ids"].shape[0]

        ids = ds.tokenizer(texto, add_special_tokens=False)["input_ids"]
        contenido = cfg["chunk_size"] - 2
        k_esperado, pos = 0, 0
        while pos < len(ids) and k_esperado < cfg["max_chunks"]:
            fin_pos = min(pos + contenido, len(ids))
            k_esperado += 1
            if fin_pos == len(ids):
                break
            pos += cfg["chunk_stride"]

    assert k_real == k_esperado, f"dataset={k_real} chunks, esperado={k_esperado}"


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
