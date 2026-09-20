"""Almacén compartido de veredictos: una línea por (artículo, juez).

Los jueces trabajan a ritmos incompatibles. Gemini va por API y puede recorrer
el corpus de corrido; el agente de Claude Code va por lotes dentro de una
sesión, con su cuota y su contexto. Obligarlos a votar a la vez sobre cada
artículo (como hacía el ensemble síncrono) impide usar al agente como juez.

Aquí cada juez escribe cuando puede y el consenso se deriva DESPUÉS, leyendo
todo lo acumulado. Consecuencias:

- se puede pasar Gemini por los 12.000 y el agente por los que alcance;
- se puede añadir un tercer juez meses más tarde sin re-preguntar a los otros;
- `silver_agent.py build` recalcula el silver entero sin gastar una llamada.

Formato: JSONL, una línea por voto. Si un juez vuelve a votar el mismo
artículo, gana la línea MÁS RECIENTE (permite corregir sin reescribir).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from src.agents.silver.judges import Verdict


def append_verdict(path: Path, article_id: str, verdict: Verdict) -> None:
    """Añade un voto al almacén."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"id": article_id, **verdict.to_dict()},
                           ensure_ascii=False) + "\n")


def append_verdicts(path: Path, article_id: str, verdicts: list[Verdict]) -> None:
    for v in verdicts:
        append_verdict(path, article_id, v)


def _to_verdict(row: dict) -> Verdict:
    return Verdict(
        judge=row.get("judge", "?"), model=row.get("model", ""),
        family=row.get("family", ""), dominant=row.get("dominant"),
        scores=row.get("scores") or {}, ok=bool(row.get("ok")),
        error=row.get("error"), truncated=bool(row.get("truncated")),
    )


def load_verdicts(path: Path) -> dict[str, list[Verdict]]:
    """{id: [veredicto por juez]}, quedándose con el voto más reciente de cada uno."""
    if not path.exists():
        return {}
    por_articulo: dict[str, dict[str, Verdict]] = defaultdict(dict)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            aid = row.get("id")
            if aid:
                por_articulo[aid][row.get("judge", "?")] = _to_verdict(row)
    return {aid: list(jueces.values()) for aid, jueces in por_articulo.items()}


def judged_ids(path: Path, judge: str | None = None) -> set[str]:
    """Artículos que ya tienen voto (de un juez concreto, si se indica)."""
    if not path.exists():
        return set()
    vistos: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not row.get("id"):
                continue
            if judge is None or row.get("judge") == judge:
                vistos.add(row["id"])
    return vistos


def coverage(path: Path) -> dict[str, int]:
    """Cuántos artículos ha votado cada juez."""
    conteo: dict[str, int] = defaultdict(int)
    for verdicts in load_verdicts(path).values():
        for v in verdicts:
            conteo[v.judge] += 1
    return dict(conteo)
