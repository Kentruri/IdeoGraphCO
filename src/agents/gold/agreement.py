"""Krippendorff α — concordancia inter-anotador (compromiso P1.3 del anteproyecto).

Implementación desde la matriz de coincidencias (Krippendorff, 2011; Hayes &
Krippendorff, 2007), sin dependencias externas. Soporta datos faltantes
(unidades con menos de 2 anotaciones se excluyen del cálculo, como define
la métrica).

    α = 1 - Do/De

donde Do es el desacuerdo observado y De el desacuerdo esperado por azar.
La función de diferencia δ define la variante:
- nominal:  δ(c,k) = 0 si c == k, 1 si no  → para la clase dominante
- interval: δ(c,k) = (c - k)²              → para las escalas 1-5 por eje

Interpretación estándar: α ≥ 0.8 confiable (umbral del anteproyecto);
0.667 ≤ α < 0.8 aceptable solo para conclusiones tentativas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Hashable, Sequence


def _coincidence_matrix(
    units: Sequence[Sequence[Hashable]],
) -> tuple[dict[tuple[Hashable, Hashable], float], dict[Hashable, float], float]:
    """Construye la matriz de coincidencias a partir de unidades anotadas.

    Args:
        units: lista de unidades; cada unidad es la lista de valores que le
            asignaron los anotadores (sin None). Unidades con < 2 valores
            se ignoran.

    Returns:
        (o, n_c, n): coincidencias por par ordenado de valores, totales por
        valor, y total general.
    """
    o: dict[tuple[Hashable, Hashable], float] = defaultdict(float)
    for values in units:
        m = len(values)
        if m < 2:
            continue
        for i, c in enumerate(values):
            for j, k in enumerate(values):
                if i != j:
                    o[(c, k)] += 1.0 / (m - 1)

    n_c: dict[Hashable, float] = defaultdict(float)
    for (c, _k), count in o.items():
        n_c[c] += count
    n = sum(n_c.values())
    return o, n_c, n


def krippendorff_alpha(
    units: Sequence[Sequence[Hashable]],
    level: str = "nominal",
) -> float | None:
    """Calcula Krippendorff α para una lista de unidades anotadas.

    Args:
        units: cada unidad = valores asignados por los anotadores que la
            calificaron (2+ para que cuente). Para level="interval" los
            valores deben ser numéricos.
        level: "nominal" (clase dominante) o "interval" (escalas 1-5).

    Returns:
        α en (-1, 1], o None si no hay unidades pareables. Si no hay
        variabilidad alguna (todos los valores idénticos), devuelve 1.0.
    """
    if level not in ("nominal", "interval"):
        raise ValueError(f"level desconocido: {level!r}")

    pairable = [
        [v for v in values if v is not None]
        for values in units
    ]
    pairable = [values for values in pairable if len(values) >= 2]
    if not pairable:
        return None

    o, n_c, n = _coincidence_matrix(pairable)

    if level == "nominal":
        delta = lambda c, k: 0.0 if c == k else 1.0  # noqa: E731
    else:
        delta = lambda c, k: (float(c) - float(k)) ** 2  # noqa: E731

    do = sum(count * delta(c, k) for (c, k), count in o.items()) / n

    values_list = list(n_c)
    de_num = sum(
        n_c[c] * n_c[k] * delta(c, k)
        for c in values_list
        for k in values_list
        if c != k
    )
    de = de_num / (n * (n - 1))

    if de == 0:
        # Sin desacuerdo esperado: todos los valores son idénticos.
        return 1.0
    return 1.0 - do / de


def percent_agreement(units: Sequence[Sequence[Hashable]]) -> float | None:
    """Acuerdo bruto (%) sobre unidades con 2+ anotaciones — complementa α."""
    pairable = [
        [v for v in values if v is not None]
        for values in units
    ]
    pairable = [values for values in pairable if len(values) >= 2]
    if not pairable:
        return None
    agreements = sum(1 for values in pairable if len(set(values)) == 1)
    return agreements / len(pairable)
