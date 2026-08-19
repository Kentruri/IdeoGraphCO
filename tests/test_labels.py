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
