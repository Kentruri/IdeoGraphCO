"""Regla de consenso entre jueces. Funciones puras, sin I/O ni LLM.

La decisión de diseño importante está en qué se hace con el DESACUERDO. La
opción obvia —descartar el artículo— sesga el silver: elimina sistemáticamente
los casos difíciles, así que el conjunto de entrenamiento queda más fácil que
la realidad y que el gold humano (que no tiene ese filtro). El modelo parece
mejor en validación de lo que es en test, y las clases intrínsecamente
ambiguas se vacían.

Por eso aquí el desacuerdo NO se descarta: se registra la etiqueta mayoritaria
con su `status` y su `agreement`, y `accepted` dice si supera la regla pedida.
Quien entrena decide: filtrar por `accepted`, o ponderar por `agreement`.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from src.agents.silver.judges import Verdict

RULES = ("unanimous", "majority")

# Estados posibles de un artículo tras el consenso.
UNANIME = "unanime"              # todos los jueces válidos (≥2) coinciden
MAYORIA = "mayoria"              # más de la mitad coincide, pero no todos
DISCREPANCIA = "discrepancia"    # nadie pasa de la mitad (empate o pluralidad)
UNICO = "unico"                  # solo un juez emitió veredicto: no hay con quién comparar
SIN_VEREDICTO = "sin_veredicto"  # ningún juez válido


@dataclass(frozen=True)
class Consensus:
    label: str | None
    status: str
    accepted: bool           # ¿supera la regla pedida?
    agreement: float         # fracción de jueces válidos que votó `label`
    votes: dict[str, int] = field(default_factory=dict)
    n_judges: int = 0
    n_valid: int = 0

    def to_dict(self) -> dict:
        return {
            "label": self.label, "status": self.status, "accepted": self.accepted,
            "agreement": round(self.agreement, 4), "votes": dict(self.votes),
            "n_judges": self.n_judges, "n_valid": self.n_valid,
        }


def resolve(verdicts: list[Verdict], rule: str = "majority") -> Consensus:
    """Combina los veredictos de un artículo.

    `rule` fija qué cuenta como aceptado:
      - "unanimous": solo UNANIME.
      - "majority":  UNANIME o MAYORIA.
    El resto (DISCREPANCIA, UNICO) conserva la etiqueta más votada pero con
    `accepted=False`; SIN_VEREDICTO no tiene etiqueta.
    """
    if rule not in RULES:
        raise ValueError(f"Regla desconocida: {rule!r}. Opciones: {RULES}")

    valid = [v for v in verdicts if v.ok and v.dominant]
    n, k = len(verdicts), len(valid)
    if k == 0:
        return Consensus(None, SIN_VEREDICTO, False, 0.0, {}, n, 0)

    votes = Counter(v.dominant for v in valid)
    top_label, top = votes.most_common(1)[0]
    tied = sum(1 for c in votes.values() if c == top) > 1
    agreement = top / k

    if k == 1:
        # Con un solo veredicto no hay acuerdo que medir. Se conserva la
        # etiqueta —es mejor que nada— pero nunca se acepta como consenso.
        return Consensus(top_label, UNICO, False, agreement, dict(votes), n, k)

    if not tied and top == k:
        status = UNANIME
    elif not tied and top * 2 > k:
        status = MAYORIA
    else:
        status = DISCREPANCIA
        # En empate la "mayoritaria" es arbitraria: mejor no fingir una.
        if tied:
            top_label = None
            agreement = 0.0

    accepted = status == UNANIME or (rule == "majority" and status == MAYORIA)
    return Consensus(top_label, status, accepted, agreement, dict(votes), n, k)


def mean_scores(verdicts: list[Verdict]) -> dict[str, float]:
    """Media por eje de los scores de los jueces válidos (señal secundaria)."""
    valid = [v for v in verdicts if v.ok and v.scores]
    if not valid:
        return {}
    axes = valid[0].scores.keys()
    return {
        axis: round(sum(v.scores.get(axis, 0.0) for v in valid) / len(valid), 4)
        for axis in axes
    }
