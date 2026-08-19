"""Tests de Krippendorff α (src/agents/gold/agreement.py)."""

import pytest

from src.agents.gold.agreement import krippendorff_alpha, percent_agreement


def test_perfect_agreement_is_one():
    units = [["a", "a"], ["b", "b"], ["c", "c"]]
    assert krippendorff_alpha(units, level="nominal") == pytest.approx(1.0)


def test_nominal_hand_computed_case():
    # 2 anotadores, 4 unidades: (a,a), (a,b), (b,b), (b,b)
    # Coincidencias: o_aa=2, o_ab=o_ba=1, o_bb=4 → n_a=3, n_b=5, n=8
    # Do = 2/8 = 0.25 ; De = (3·5 + 5·3)/(8·7) = 30/56
    # α = 1 − 0.25/(30/56) = 1 − 14/30 = 0.5333…
    units = [["a", "a"], ["a", "b"], ["b", "b"], ["b", "b"]]
    alpha = krippendorff_alpha(units, level="nominal")
    assert alpha == pytest.approx(1 - 14 / 30, abs=1e-9)


def test_units_with_missing_values_are_excluded():
    units = [["a", "a"], ["b", None], [None, None], ["a", "a"]]
    # Solo cuentan las dos unidades con 2 valores → acuerdo perfecto
    assert krippendorff_alpha(units, level="nominal") == pytest.approx(1.0)
    assert percent_agreement(units) == pytest.approx(1.0)


def test_no_pairable_units_returns_none():
    assert krippendorff_alpha([["a"], [None, "b"]], level="nominal") is None
    assert percent_agreement([["a"]]) is None


def test_interval_penalizes_by_distance():
    # Desacuerdo 1-2 (cercano) debe dar α mayor que desacuerdo 1-5 (extremo)
    close = [[1, 2], [3, 3], [4, 4], [2, 2], [5, 5]]
    far = [[1, 5], [3, 3], [4, 4], [2, 2], [5, 5]]
    alpha_close = krippendorff_alpha(close, level="interval")
    alpha_far = krippendorff_alpha(far, level="interval")
    assert alpha_close > alpha_far


def test_invalid_level_raises():
    with pytest.raises(ValueError):
        krippendorff_alpha([["a", "a"]], level="ratio")
