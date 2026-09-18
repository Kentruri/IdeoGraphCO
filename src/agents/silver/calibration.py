"""Calibración del ensemble contra el gold humano. Funciones puras.

Responde a la pregunta que decide si el consenso sirve para algo: ¿el acuerdo
entre jueces PREDICE el acierto? Si P(correcto | unánime) es 0,88 y
P(correcto | discrepancia) es 0,45, la regla está justificada con datos. Si
la brecha es pequeña, el consenso no compra nada y solo tira artículos.

Entrada: los registros de `<silver>.verdicts.jsonl` (uno por artículo, con
los veredictos de cada juez) y las etiquetas humanas del gold
(`annotation/gold_set_v2_labeled.jsonl`). Salida: un dict con las métricas
y `render_report` para el Markdown citable en el informe (P1.3).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

from src.agents.gold.agreement import krippendorff_alpha, percent_agreement
from src.agents.silver.consensus import RULES, resolve
from src.agents.silver.judges import Verdict


def _verdicts_from_record(rec: dict) -> list[Verdict]:
    out = []
    for v in rec.get("verdicts", []):
        out.append(Verdict(
            judge=v["judge"], model=v.get("model", ""), family=v.get("family", ""),
            dominant=v.get("dominant"), scores=v.get("scores") or {},
            ok=bool(v.get("ok")), error=v.get("error"),
            truncated=bool(v.get("truncated")),
        ))
    return out


def calibrate(records: list[dict], gold: dict[str, str],
              rule: str = "majority") -> dict:
    """Métricas del ensemble sobre los artículos que tienen etiqueta humana.

    Args:
        records: registros de veredictos (`verdicts.jsonl`).
        gold: {id: clase humana}.
        rule: regla con la que se recalcula el consenso (permite comparar
            reglas sobre los MISMOS veredictos sin volver a pagar LLM).
    """
    if rule not in RULES:
        raise ValueError(f"Regla desconocida: {rule!r}")

    rows = [r for r in records if r.get("id") in gold]
    n = len(rows)
    if n == 0:
        return {"n": 0, "rule": rule}

    # --- por juez: precisión contra el humano ---
    per_judge: dict[str, dict] = {}
    by_judge_votes: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        truth = gold[r["id"]]
        for v in _verdicts_from_record(r):
            stats = per_judge.setdefault(v.judge, {"model": v.model, "family": v.family,
                                                   "n": 0, "ok": 0, "correct": 0})
            stats["n"] += 1
            if v.ok and v.dominant:
                stats["ok"] += 1
                stats["correct"] += int(v.dominant == truth)
                by_judge_votes[v.judge][r["id"]] = v.dominant
    for stats in per_judge.values():
        stats["accuracy"] = stats["correct"] / stats["ok"] if stats["ok"] else None
        stats["coverage"] = stats["ok"] / stats["n"] if stats["n"] else 0.0

    # --- entre jueces: α de Krippendorff por pareja ---
    pairwise = {}
    for a, b in combinations(sorted(by_judge_votes), 2):
        shared = sorted(set(by_judge_votes[a]) & set(by_judge_votes[b]))
        units = [[by_judge_votes[a][i], by_judge_votes[b][i]] for i in shared]
        pairwise[f"{a}|{b}"] = {
            "n": len(shared),
            "alpha": krippendorff_alpha(units, level="nominal") if units else None,
            "agreement": percent_agreement(units) if units else None,
        }

    # --- consenso: ¿el estado predice el acierto? ---
    by_status: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
    accepted = {"n": 0, "correct": 0}
    rejected = {"n": 0, "correct": 0}
    per_class: dict[str, dict] = defaultdict(lambda: {"gold": 0, "accepted": 0, "correct": 0})
    confusion: Counter = Counter()

    for r in rows:
        truth = gold[r["id"]]
        c = resolve(_verdicts_from_record(r), rule)
        per_class[truth]["gold"] += 1
        hit = int(c.label == truth) if c.label else 0
        by_status[c.status]["n"] += 1
        by_status[c.status]["correct"] += hit
        bucket = accepted if c.accepted else rejected
        bucket["n"] += 1
        bucket["correct"] += hit
        if c.accepted:
            per_class[truth]["accepted"] += 1
            per_class[truth]["correct"] += hit
            if c.label:
                confusion[(truth, c.label)] += 1

    def _acc(d: dict) -> float | None:
        return d["correct"] / d["n"] if d["n"] else None

    for s in by_status.values():
        s["accuracy"] = _acc(s)
    for c in per_class.values():
        c["recall_accepted"] = c["correct"] / c["gold"] if c["gold"] else None
        c["coverage"] = c["accepted"] / c["gold"] if c["gold"] else None

    return {
        "n": n,
        "rule": rule,
        "per_judge": per_judge,
        "pairwise": pairwise,
        "by_status": dict(by_status),
        "accepted": {**accepted, "accuracy": _acc(accepted), "coverage": accepted["n"] / n},
        "rejected": {**rejected, "accuracy": _acc(rejected), "coverage": rejected["n"] / n},
        "per_class": dict(per_class),
        "confusion_accepted": {f"{t}→{p}": k for (t, p), k in confusion.most_common()
                               if t != p},
    }


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.1f} %"


def render_report(result: dict) -> str:
    """Markdown para el informe. Cita las cifras, no las adorna."""
    if not result.get("n"):
        return "# Calibración del ensemble\n\nSin artículos del gold con veredictos.\n"

    L = ["# Calibración del ensemble contra el gold humano", "",
         f"- Artículos con etiqueta humana y veredictos: **{result['n']}**",
         f"- Regla de consenso evaluada: `{result['rule']}`", "",
         "## Cada juez frente al humano", "",
         "| juez | modelo | familia | cobertura | precisión |", "|---|---|---|---|---|"]
    for name, s in sorted(result["per_judge"].items()):
        L.append(f"| {name} | `{s['model']}` | {s['family']} | {_pct(s['coverage'])} | "
                 f"**{_pct(s['accuracy'])}** |")

    if result["pairwise"]:
        L += ["", "## Acuerdo entre jueces (Krippendorff α, nominal)", "",
              "| pareja | n | α | acuerdo simple |", "|---|---|---|---|"]
        for pair, s in result["pairwise"].items():
            a = "—" if s["alpha"] is None else f"{s['alpha']:.3f}"
            L.append(f"| {pair} | {s['n']} | {a} | {_pct(s['agreement'])} |")
        L += ["", "α ≥ 0,8 es el umbral del anteproyecto para anotadores humanos; entre",
              "modelos, α alto con familias DISTINTAS es evidencia; con la misma",
              "familia solo mide consistencia."]

    L += ["", "## ¿El acuerdo predice el acierto?", "",
          "| estado del consenso | artículos | precisión |", "|---|---|---|"]
    for status in ("unanime", "mayoria", "discrepancia", "unico", "sin_veredicto"):
        s = result["by_status"].get(status)
        if s:
            L.append(f"| {status} | {s['n']} | **{_pct(s['accuracy'])}** |")
    acc, rej = result["accepted"], result["rejected"]
    L += ["",
          f"Con la regla `{result['rule']}`: se **aceptan {acc['n']}** ({_pct(acc['coverage'])} "
          f"del gold) con precisión **{_pct(acc['accuracy'])}**; se rechazan {rej['n']} "
          f"cuya etiqueta mayoritaria acierta el {_pct(rej['accuracy'])}.", "",
          "Lectura: si la precisión de lo aceptado no supera claramente la de lo",
          "rechazado, el consenso no está filtrando errores, solo dificultad."]

    L += ["", "## Por clase (etiqueta humana)", "",
          "| clase | en el gold | aceptados | cobertura | acierto sobre el gold |",
          "|---|---|---|---|---|"]
    for cls, c in sorted(result["per_class"].items()):
        L.append(f"| {cls} | {c['gold']} | {c['accepted']} | {_pct(c['coverage'])} | "
                 f"{_pct(c['recall_accepted'])} |")
    L += ["", "Una cobertura muy desigual entre clases es la señal de que el consenso",
          "vacía las clases ambiguas y distorsiona el prior del entrenamiento."]

    if result["confusion_accepted"]:
        L += ["", "## Confusiones más frecuentes (aceptados y aun así erróneos)", ""]
        for k, v in list(result["confusion_accepted"].items())[:10]:
            L.append(f"- {k}: {v}")
    return "\n".join(L) + "\n"
