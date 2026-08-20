"""ΔD — distancia estadística entre dos huellas ideológicas de 8 clases.

ALCANCE: ΔD **no es un producto comprometido** del anteproyecto aprobado
(jun-2026), cuyos entregables van de P1.1 a P4.1. Una versión anterior del
documento la listaba como "P5.2"; esa referencia se corrigió en ago-2026.

Lo que sí compromete el anteproyecto es el soporte técnico de la Fase 4,
"Interfaz Interactiva Comparativa: ... una aplicación web interactiva que
adoptará un diseño comparativo, encargado de proyectar las afinidades
ideológicas". ΔD cuantifica esa comparación entre dos distribuciones, así que
es infraestructura de P4.1, no un producto aparte. Si aparece en la tesis,
debe presentarse como decisión de implementación del prototipo.

Implementación por defecto: **distancia de Jensen-Shannon** (raíz cuadrada
de la divergencia de Jensen-Shannon con logaritmo base 2), porque:
- es SIMÉTRICA (ΔD(P,Q) = ΔD(Q,P)) — a diferencia de KL;
- está ACOTADA en [0, 1] con log₂ — directamente interpretable en la UI
  (0 = huellas idénticas, 1 = disjuntas);
- es una métrica válida (cumple la desigualdad triangular);
- está definida aunque alguna clase tenga probabilidad 0 (KL diverge).

Definición, con M = ½(P + Q):

    JSD(P‖Q) = ½·KL(P‖M) + ½·KL(Q‖M)
    ΔD(P, Q) = √JSD(P‖Q)                       ∈ [0, 1] (log base 2)

Alternativas disponibles (para el análisis de sensibilidad del documento):
- hellinger:        H(P,Q) = (1/√2)·‖√P − √Q‖₂            ∈ [0, 1]
- total_variation:  TV(P,Q) = ½·Σ|pᵢ − qᵢ|                 ∈ [0, 1]
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from src.core.schema import IDEOLOGY_CLASSES

_EPSILON = 1e-12


def _as_vector(dist: Mapping[str, float] | Sequence[float]) -> list[float]:
    """Acepta dict {clase: prob} o secuencia en el orden canónico de clases."""
    if isinstance(dist, Mapping):
        vector = [float(dist[cls]) for cls in IDEOLOGY_CLASSES]
    else:
        vector = [float(v) for v in dist]
    if len(vector) != len(IDEOLOGY_CLASSES):
        raise ValueError(
            f"Se esperaban {len(IDEOLOGY_CLASSES)} probabilidades, "
            f"llegaron {len(vector)}"
        )
    total = sum(vector)
    if total <= 0:
        raise ValueError("La distribución no puede sumar 0")
    if any(v < 0 for v in vector):
        raise ValueError("Las probabilidades no pueden ser negativas")
    # Re-normalizar ruido de redondeo (p.ej. sumas de 0.9999)
    return [v / total for v in vector]


def jensen_shannon_distance(
    p: Mapping[str, float] | Sequence[float],
    q: Mapping[str, float] | Sequence[float],
) -> float:
    """ΔD por defecto: distancia de Jensen-Shannon (log₂) ∈ [0, 1]."""
    vp, vq = _as_vector(p), _as_vector(q)
    m = [(a + b) / 2 for a, b in zip(vp, vq)]

    def _kl(x: list[float], y: list[float]) -> float:
        return sum(
            a * math.log2(a / max(b, _EPSILON))
            for a, b in zip(x, y) if a > _EPSILON
        )

    jsd = 0.5 * _kl(vp, m) + 0.5 * _kl(vq, m)
    # Acotar ruido numérico (jsd ∈ [0, 1] con log₂)
    return math.sqrt(max(0.0, min(1.0, jsd)))


def hellinger_distance(
    p: Mapping[str, float] | Sequence[float],
    q: Mapping[str, float] | Sequence[float],
) -> float:
    """Distancia de Hellinger ∈ [0, 1]."""
    vp, vq = _as_vector(p), _as_vector(q)
    return math.sqrt(
        sum((math.sqrt(a) - math.sqrt(b)) ** 2 for a, b in zip(vp, vq))
    ) / math.sqrt(2)


def total_variation_distance(
    p: Mapping[str, float] | Sequence[float],
    q: Mapping[str, float] | Sequence[float],
) -> float:
    """Distancia de variación total ∈ [0, 1]."""
    vp, vq = _as_vector(p), _as_vector(q)
    return 0.5 * sum(abs(a - b) for a, b in zip(vp, vq))


_METHODS = {
    "jensen_shannon": jensen_shannon_distance,
    "hellinger": hellinger_distance,
    "total_variation": total_variation_distance,
}


def delta_d(
    p: Mapping[str, float] | Sequence[float],
    q: Mapping[str, float] | Sequence[float],
    method: str = "jensen_shannon",
) -> float:
    """ΔD entre dos distribuciones sobre las 8 clases ideológicas."""
    if method not in _METHODS:
        raise ValueError(f"Método desconocido: {method!r}. Opciones: {list(_METHODS)}")
    return _METHODS[method](p, q)
