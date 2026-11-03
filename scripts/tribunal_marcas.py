#!/usr/bin/env python3
"""Agrega las marcas que los jueces dejaron en los comentarios de sus decisiones.

Los comentarios no viajan a `votos.jsonl` — el parser los descarta — así que
solo sobreviven en los `decisiones_*.txt`, y únicamente porque se ingirió con
`--keep-batch`. Este script los recoge antes de que se pierdan.
"""

from __future__ import annotations

import collections
import re
from pathlib import Path

TRIB = Path(__file__).resolve().parent.parent / "annotation" / "calibration" / "tribunal"
JUECES = ("opus", "sonnet", "haiku")

# Marcas pedidas en los encargos + las que los jueces inventaron por su cuenta.
MARCAS = {
    "promoción": r"promoc", "tecnocrático": r"tecnocr", "contrapuntal": r"contrapunt",
    "casi-soberanismo": r"casi-?sob", "casi-doctrinarismo": r"casi-?doc",
    "verificación": r"verificaci[óo]n|fact-?check", "desvío del codebook": r"\bDESVIO\b|desv[íi]o",
}
CAL = re.compile(r"\bCAL-([A-Z]+)\b")


def main() -> None:
    marcas = {m: collections.Counter() for m in MARCAS}
    cal = collections.Counter()
    lineas = collections.Counter()

    for juez in JUECES:
        for f in sorted((TRIB / juez).glob("decisiones_*.txt")):
            for linea in f.read_text(encoding="utf-8", errors="replace").splitlines():
                if "#" not in linea:
                    continue
                com = linea.split("#", 1)[1]
                lineas[juez] += 1
                for nombre, pat in MARCAS.items():
                    if re.search(pat, com, re.I):
                        marcas[nombre][juez] += 1
                for etiqueta in CAL.findall(com):
                    cal[etiqueta] += 1

    ancho = max(len(m) for m in MARCAS)
    print("  Líneas con comentario: " + " · ".join(f"{j}={lineas[j]:,}" for j in JUECES))
    print(f"\n  {'marca':<{ancho}}" + "".join(f"{j:>9}" for j in JUECES) + f"{'total':>8}")
    for m in MARCAS:
        c = marcas[m]
        t = sum(c.values())
        if t:
            print(f"  {m:<{ancho}}" + "".join(f"{c[j]:>9}" for j in JUECES) + f"{t:>8}")

    if cal:
        print("\n  Problemas de calidad del texto (etiquetas CAL-*)")
        for etiqueta, n in cal.most_common(14):
            print(f"    CAL-{etiqueta:<12} {n:5}")


if __name__ == "__main__":
    main()
