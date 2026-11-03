"""Pesos por clase de la pérdida (src/training/class_weights.py)."""

import pytest

from src.training.class_weights import class_weights


def test_media_uno_y_orden_inverso():
    w = class_weights([3892, 1944, 431, 205], "inverse")
    assert sum(w) / len(w) == pytest.approx(1.0, abs=1e-3)
    assert w == sorted(w)            # la clase más escasa pesa más


def test_inverse_iguala_contribucion():
    counts = [400, 100]
    w = class_weights(counts, "inverse")
    assert counts[0] * w[0] == pytest.approx(counts[1] * w[1], rel=1e-3)


def test_sqrt_inverse_es_mas_suave():
    counts = [2000, 100]
    inv = class_weights(counts, "inverse")
    raiz = class_weights(counts, "sqrt_inverse")
    assert raiz[1] / raiz[0] == pytest.approx((inv[1] / inv[0]) ** 0.5, rel=1e-3)


def test_clase_vacia_no_rompe():
    w = class_weights([10, 0, 10], "inverse")
    assert w[1] == 0.0
    assert w[0] == pytest.approx(1.0)


def test_modo_desconocido():
    with pytest.raises(ValueError):
        class_weights([1, 2], "focal")
