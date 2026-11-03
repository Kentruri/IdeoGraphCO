#!/usr/bin/env python3
"""Calibración del codebook: el agente re-etiqueta gold ya anotado y se compara.

Mide si una revisión del codebook cambia lo que se esperaba. NO produce silver:
escribe en `annotation/calibration/`, nunca en `data/silver/`, porque los
artículos son del conjunto de PRUEBA y un veredicto suyo en el almacén silver
sería la fuga que `tests/test_gold_isolation.py` vigila.

    batch   genera los lotes a leer (ciego: no muestra la etiqueta humana)
    ingest  registra las decisiones de un lote
    report  compara contra el anotador humano

Formato de decisión, según §2.2 del codebook v1.1 (procedimiento abreviado):

    n  clase  fuerza

`fuerza` es el puntaje 1-5 de ESA clase. Si es <= 2 la etiqueta pasa a
`sin_encuadre` por la regla de umbral (§2.1, regla 3); el script lo aplica.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.gold.agreement import krippendorff_alpha  # noqa: E402
from src.core.schema import IDEOLOGY_CLASSES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "annotation" / "gold_set_v2.jsonl"
HUMANO = ROOT / "annotation" / "gold_set_v2_juan.json"
OUT = ROOT / "annotation" / "calibration"
VEREDICTOS = OUT / "veredictos_agente.jsonl"
MUESTRA = OUT / "muestra.json"

HEAD_CHARS = 2400
SIN_ENCUADRE = "sin_encuadre"
ALIAS = {"pop": "populismo", "inst": "institucionalismo", "pers": "personalismo",
         "doc": "doctrinarismo", "sob": "soberanismo", "glob": "globalismo",
         "cons": "conservadurismo", "prog": "progresismo", "sin": SIN_ENCUADRE}


def cargar_humano() -> dict[str, str]:
    """{article_id: clase} de las anotaciones humanas vigentes."""
    out = {}
    for t in json.loads(HUMANO.read_text(encoding="utf-8")):
        anns = [a for a in t.get("annotations", []) if not a.get("was_cancelled")]
        if not anns:
            continue
        for item in anns[-1].get("result", []) or []:
            if item.get("from_name") == "clase_dominante":
                ch = (item.get("value") or {}).get("choices") or []
                if ch:
                    out[t["data"]["id"]] = ch[0]
    return out


def cargar_gold() -> dict[str, dict]:
    return {a["id"]: a for a in (json.loads(linea) for linea in
            GOLD.read_text(encoding="utf-8").splitlines() if linea.strip())}


def cmd_batch(args: argparse.Namespace) -> None:
    humano, gold = cargar_humano(), cargar_gold()
    ids = sorted(set(humano) & set(gold))
    random.Random(args.seed).shuffle(ids)
    ids = ids[: args.n]

    OUT.mkdir(parents=True, exist_ok=True)
    MUESTRA.write_text(json.dumps(
        {"seed": args.seed, "n": len(ids), "size": args.size, "ids": ids},
        indent=2), encoding="utf-8")

    for b, inicio in enumerate(range(0, len(ids), args.size), 1):
        trozo = ids[inicio : inicio + args.size]
        lineas = [f"LOTE {b} · {len(trozo)} artículos · decide: n clase fuerza(1-5)", ""]
        for i, aid in enumerate(trozo, inicio + 1):
            a = gold[aid]
            cuerpo = a["text"][:HEAD_CHARS]
            if len(a["text"]) > HEAD_CHARS:
                cuerpo += " […]"
            lineas += [f"[{i}] {a.get('title', '').strip()}", "", cuerpo, "", "-" * 78, ""]
        p = OUT / f"lote_{b:02d}.txt"
        p.write_text("\n".join(lineas), encoding="utf-8")
        print(f"  {p.relative_to(ROOT)}  ({len(trozo)} artículos)")
    print(f"\n✓ {len(ids)} artículos · muestra anclada en {MUESTRA.relative_to(ROOT)}")


def cmd_ingest(args: argparse.Namespace) -> None:
    muestra = json.loads(MUESTRA.read_text(encoding="utf-8"))
    ids = muestra["ids"]
    registros, errores = [], []

    for ln, linea in enumerate(Path(args.decisions).read_text(encoding="utf-8").splitlines(), 1):
        linea = linea.split("#")[0].strip()
        if not linea:
            continue
        partes = linea.split()
        if len(partes) < 3:
            errores.append(f"línea {ln}: se esperaba 'n clase fuerza' → {linea!r}")
            continue
        try:
            n, fuerza = int(partes[0]), int(partes[2])
        except ValueError:
            errores.append(f"línea {ln}: n y fuerza deben ser enteros → {linea!r}")
            continue
        clase = ALIAS.get(partes[1].lower(), partes[1].lower())
        if clase not in IDEOLOGY_CLASSES and clase != SIN_ENCUADRE:
            errores.append(f"línea {ln}: clase desconocida {clase!r}")
            continue
        if not 1 <= fuerza <= 5:
            errores.append(f"línea {ln}: fuerza fuera de 1-5 → {fuerza}")
            continue
        if not 1 <= n <= len(ids):
            errores.append(f"línea {ln}: n={n} fuera de la muestra")
            continue
        # Regla de umbral del codebook v1.1 §2.1(3): el máximo <= 2 no es encuadre.
        final = SIN_ENCUADRE if fuerza <= 2 else clase
        registros.append({"id": ids[n - 1], "n": n, "clase_bruta": clase,
                          "fuerza": fuerza, "clase": final})

    if errores:
        print("✗ " + "\n✗ ".join(errores))
        raise SystemExit(1)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(VEREDICTOS, "a", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    umbral = sum(1 for r in registros if r["clase"] == SIN_ENCUADRE)
    print(f"✓ {len(registros)} decisiones · {umbral} pasaron a sin_encuadre por umbral")


def cmd_report(args: argparse.Namespace) -> None:
    humano = cargar_humano()
    vistos: dict[str, dict] = {}
    for linea in VEREDICTOS.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            r = json.loads(linea)
            vistos[r["id"]] = r  # el último voto manda
    n = len(vistos)
    if not n:
        raise SystemExit("✗ sin veredictos.")

    mio = collections.Counter(r["clase"] for r in vistos.values())
    suyo = collections.Counter(humano[i] for i in vistos)
    ancho = max(len(c) for c in set(mio) | set(suyo))

    print(f"\n{'':<{ancho}}   humano(v1.0)      agente(v1.1)")
    print("-" * (ancho + 34))
    for c in sorted(set(mio) | set(suyo), key=lambda c: -(mio[c] + suyo[c])):
        print(f"{c:<{ancho}}   {suyo[c]:4} {suyo[c]/n:6.1%}      {mio[c]:4} {mio[c]/n:6.1%}")

    iguales = sum(1 for i, r in vistos.items() if r["clase"] == humano[i])
    alfa = krippendorff_alpha([[humano[i], r["clase"]] for i, r in vistos.items()])
    print(f"\n  n = {n}   acuerdo bruto = {iguales/n:.1%}   α (nominal) = "
          f"{alfa:.3f}" if alfa is not None else "")

    inst = {i: r for i, r in vistos.items() if humano[i] == "institucionalismo"}
    if inst:
        print(f"\n  Los {len(inst)} que el humano llamó institucionalismo, ahora:")
        for c, k in collections.Counter(r["clase"] for r in inst.values()).most_common():
            print(f"    {c:<{ancho}}  {k:4}  {k/len(inst):6.1%}")

    otros = {i: r for i, r in vistos.items() if humano[i] != "institucionalismo"}
    if otros:
        ok = sum(1 for i, r in otros.items() if r["clase"] == humano[i])
        print(f"\n  Control — los {len(otros)} que el humano NO llamó institucionalismo:")
        print(f"    coincidencias: {ok}/{len(otros)} = {ok/len(otros):.1%}")
        for i, r in sorted(otros.items(), key=lambda kv: humano[kv[0]]):
            if r["clase"] != humano[i]:
                print(f"      humano={humano[i]:<{ancho}} agente={r['clase']} (f={r['fuerza']})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("batch", help="genera los lotes a leer")
    b.add_argument("--n", type=int, default=100)
    b.add_argument("--size", type=int, default=25)
    b.add_argument("--seed", type=int, default=11)
    b.set_defaults(func=cmd_batch)

    i = sub.add_parser("ingest", help="registra las decisiones de un lote")
    i.add_argument("--decisions", required=True)
    i.set_defaults(func=cmd_ingest)

    r = sub.add_parser("report", help="compara contra el anotador humano")
    r.set_defaults(func=cmd_report)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
