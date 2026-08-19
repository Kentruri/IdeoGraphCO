"""Tests de la métrica ΔD (src/inference/delta.py)."""

import pytest

from src.core.schema import IDEOLOGY_CLASSES, NUM_CLASSES
from src.inference.delta import (
    delta_d,
    hellinger_distance,
    jensen_shannon_distance,
    total_variation_distance,
)

UNIFORM = [1 / NUM_CLASSES] * NUM_CLASSES
ONE_HOT_A = [1.0] + [0.0] * (NUM_CLASSES - 1)
ONE_HOT_B = [0.0, 1.0] + [0.0] * (NUM_CLASSES - 2)


def test_identical_distributions_give_zero():
    for fn in (jensen_shannon_distance, hellinger_distance, total_variation_distance):
        assert fn(UNIFORM, UNIFORM) == pytest.approx(0.0, abs=1e-9)


def test_disjoint_distributions_give_one():
    # Distribuciones disjuntas → distancia máxima = 1 en las tres métricas
    for fn in (jensen_shannon_distance, hellinger_distance, total_variation_distance):
        assert fn(ONE_HOT_A, ONE_HOT_B) == pytest.approx(1.0, abs=1e-6)


def test_symmetry():
    p = [0.4, 0.2, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05]
    assert jensen_shannon_distance(p, UNIFORM) == pytest.approx(
        jensen_shannon_distance(UNIFORM, p)
    )


def test_accepts_dict_in_canonical_order():
    p = {cls: 1 / NUM_CLASSES for cls in IDEOLOGY_CLASSES}
    q = dict(zip(IDEOLOGY_CLASSES, ONE_HOT_A))
    assert delta_d(p, q) == pytest.approx(jensen_shannon_distance(UNIFORM, ONE_HOT_A))


def test_renormalizes_rounding_noise():
    noisy = [v * 0.9999 for v in UNIFORM]
    assert delta_d(noisy, UNIFORM) == pytest.approx(0.0, abs=1e-6)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        delta_d([0.5, 0.5], UNIFORM)  # dimensión incorrecta
    with pytest.raises(ValueError):
        delta_d([0.0] * NUM_CLASSES, UNIFORM)  # suma cero
    with pytest.raises(ValueError):
        delta_d(UNIFORM, UNIFORM, method="euclidea")  # método desconocido
