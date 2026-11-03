#!/usr/bin/env python3
"""Auditoría P1.3: el tribunal del silver contra el anotador humano, sobre el gold.

El anteproyecto pide medir la concordancia (α) entre las etiquetas del agente
y las de los investigadores sobre muestras ALEATORIAS. El gold es exactamente
eso —una muestra aleatoria estratificada del mismo corpus—, y ya lo anota un
humano. Así que el tribunal lo vota con el MISMO protocolo que el silver
(haiku + sonnet, opus si discrepan, codebook vigente) y se compara.

Los votos van a `annotation/calibration/tribunal_v12/`: el gold es el test y
sus etiquetas de juez nunca tocan data/silver ni el entrenamiento.

La calibración del 12-oct (`tribunal/`) votó con el codebook v1.1, antes de
las capas de entonación, sustancia y macroeconomía: no mide el silver actual.

    python scripts/tribunal_auditoria.py preparar     # añade lo nuevo que anotó el humano
    python scripts/tribunal_auditoria.py correr --cap-semanal 74
    python scripts/tribunal_auditoria.py reporte
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import silver_estado as S  # noqa: E402
from scripts.filter_runner import weekly_usage  # noqa: E402
from src.agents.gold.agreement import krippendorff_alpha  # noqa: E402

ROOT = S.ROOT
BASE = ROOT / "annotation" / "calibration" / "tribunal_v12"
CORPUS = BASE / "corpus.jsonl"
CORPUS_OPUS = BASE / "corpus_opus.jsonl"
HUMANO = BASE / "humano.json"
EXPORTS = sorted((ROOT / "annotation").glob("gold_set_v2_*.json"))
GOLD_JSONL = ROOT / "annotation" / "gold_set_v2.jsonl"
PYTHON = str(ROOT / ".venv" / "bin" / "python")


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def etiquetas_humanas() -> dict[str, str]:
    """{id: clase} de los exports de Label Studio (la última anotación válida)."""
    out: dict[str, str] = {}
    for f in EXPORTS:
        if f.name in ("gold_set_v2_ids.json", "gold_set_v2_assignment.json"):
            continue
        for t in json.loads(f.read_text(encoding="utf-8")):
            anns = [a for a in t.get("annotations", []) if not a.get("was_cancelled")]
            for a in anns[-1:]:
                for r in a.get("result", []):
                    if r.get("from_name") == "clase_dominante":
                        out[t["data"]["id"]] = r["value"]["choices"][0]
    return out


def _ids(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [json.loads(x)["id"] for x in path.open(encoding="utf-8") if x.strip()]


def votos(juez: str) -> dict[str, str]:
    return S._union_en(BASE, f"votos_{juez}*.jsonl")


def cmd_preparar(args: argparse.Namespace) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    humano = etiquetas_humanas()
    gold = {json.loads(x)["id"]: json.loads(x) for x in GOLD_JSONL.open(encoding="utf-8") if x.strip()}
    fuera = set(humano) - set(gold)
    if fuera:
        raise SystemExit(f"✗ {len(fuera)} etiquetas humanas de artículos que no son del gold.")
    ya = set(_ids(CORPUS))
    nuevos = sorted(i for i in humano if i not in ya)
    with CORPUS.open("a", encoding="utf-8") as f:
        for i in nuevos:
            a = gold[i]
            f.write(json.dumps({"id": i, "title": a.get("title", ""), "text": a.get("text", "")},
                               ensure_ascii=False) + "\n")
    HUMANO.write_text(json.dumps(humano, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"  humano: {len(humano):,} etiquetas · corpus: {len(ya):,} + {len(nuevos):,} nuevos")


def necesita_opus() -> list[str]:
    h, s, o = votos("haiku"), votos("sonnet"), votos("opus")
    out = []
    for i in _ids(CORPUS):
        if i in o or i not in h or i not in s:
            continue
        if S.mayoria_perezosa({"haiku": h[i], "sonnet": s[i]})[1] == S.PENDIENTE:
            out.append(i)
    return out


def vivo(tag: str) -> bool:
    pidf = BASE / f"runner_{tag}.pid"
    try:
        os.kill(int(pidf.read_text().strip()), 0)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return False
    return True


def lanza(juez: str, sufijo: str, corpus: Path, cap: float, budget: int) -> None:
    logf = BASE / f"runner_{juez}{sufijo}.log"
    with logf.open("a", encoding="utf-8") as f:
        subprocess.Popen(
            [PYTHON, "-u", str(ROOT / "scripts" / "silver_runner.py"),
             "--juez", juez, "--sufijo", sufijo, "--corpus", str(corpus.relative_to(ROOT)),
             "--cap-semanal", str(cap), "--budget", str(budget),
             "--calibracion", str(BASE.relative_to(ROOT))],
            stdout=f, stderr=subprocess.STDOUT, cwd=ROOT, start_new_session=True)


def cmd_correr(args: argparse.Namespace) -> None:
    claude_bin = shutil.which("claude") or "claude"
    (BASE / "auditoria.pid").write_text(str(os.getpid()), encoding="utf-8")
    subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())], start_new_session=True)
    gold = {json.loads(x)["id"]: json.loads(x) for x in CORPUS.open(encoding="utf-8") if x.strip()}
    log(f"auditoría · {len(gold):,} artículos · tope semanal {args.cap_semanal:.0f} %")
    while True:
        uso = weekly_usage(claude_bin)
        if uso and uso[0] >= args.cap_semanal:
            log(f"⏹ semanal al {uso[0]:.0f} %. Fin.")
            return
        ya = set(_ids(CORPUS_OPUS))
        nuevos = [i for i in necesita_opus() if i not in ya]
        if nuevos:
            with CORPUS_OPUS.open("a", encoding="utf-8") as f:
                for i in nuevos:
                    f.write(json.dumps(gold[i], ensure_ascii=False) + "\n")
            log(f"   +{len(nuevos)} para opus")

        pend = {}
        for juez, suf, corpus in (("haiku", "", CORPUS), ("sonnet", "", CORPUS),
                                  ("opus", "_desempate", CORPUS_OPUS)):
            hechos = set(votos(juez))
            pend[juez] = sum(1 for i in _ids(corpus) if i not in hechos)
            arriba = pend.get("haiku", 0) + pend.get("sonnet", 0)
            if pend[juez] and not vivo(f"{juez}{suf}") and \
                    (juez != "opus" or pend[juez] >= 30 or arriba == 0):
                log(f"▶ lanzo {juez}{suf} ({pend[juez]:,} pendientes)")
                lanza(juez, suf, corpus, args.cap_semanal, args.budget)
                time.sleep(3)
        activos = sum(vivo(t) for t in ("haiku", "sonnet", "opus_desempate"))
        log(f"   pendientes {pend} · activos {activos}"
            + (f" · semanal {uso[0]:.0f} %" if uso else ""))
        if not any(pend.values()) and not activos:
            log("✓ auditoría votada. Corre `reporte`.")
            return
        time.sleep(args.intervalo)


def cmd_reporte(args: argparse.Namespace) -> None:
    humano = json.loads(HUMANO.read_text(encoding="utf-8"))
    h, s, o = votos("haiku"), votos("sonnet"), votos("opus")
    trib = {}
    for i in humano:
        v = {k: x[i] for k, x in (("haiku", h), ("sonnet", s), ("opus", o)) if i in x}
        clase, estado = S.mayoria_perezosa(v)
        if estado != S.PENDIENTE:
            trib[i] = clase or "discrepancia"
    pares = [(humano[i], trib[i]) for i in trib]
    if not pares:
        raise SystemExit("✗ Todavía no hay artículos con veredicto del tribunal.")
    acuerdo = sum(a == b for a, b in pares) / len(pares)
    print(f"  Tribunal (codebook vigente) vs humano — n={len(pares):,}")
    print(f"    acuerdo bruto {acuerdo:.1%}   α={krippendorff_alpha([list(p) for p in pares]):+.3f}")
    con = [(a, b) for a, b in pares if b in S.CLASES]
    if con:
        ok = sum(a == b for a, b in con) / len(con)
        print(f"    donde el tribunal ve encuadre (n={len(con):,}): acuerdo {ok:.1%}   "
              f"α={krippendorff_alpha([list(p) for p in con]):+.3f}")
    print(f"    el tribunal dice sin_encuadre en {sum(b == S.NF for _, b in pares) / len(pares):.1%}")
    print("\n  Confusiones más frecuentes (humano → tribunal):")
    for (a, b), n in collections.Counter(p for p in pares if p[0] != p[1]).most_common(10):
        print(f"    {a:<18} → {b:<18} {n:4}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preparar").set_defaults(func=cmd_preparar)
    p = sub.add_parser("correr")
    p.add_argument("--cap-semanal", type=float, default=74.0)
    p.add_argument("--budget", type=int, default=110_000)
    p.add_argument("--intervalo", type=float, default=180.0)
    p.set_defaults(func=cmd_correr)
    sub.add_parser("reporte").set_defaults(func=cmd_reporte)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
