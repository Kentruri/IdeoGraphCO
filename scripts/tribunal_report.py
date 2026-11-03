#!/usr/bin/env python3
"""Consenso del tribunal de tres jueces y comparación contra el anotador humano.

Solo LEE `annotation/calibration/tribunal/votos.jsonl`; no escribe en el
almacén. Pensado para correr mientras los jueces trabajan.

    python scripts/tribunal_report.py [--min-jueces 2]
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.gold.agreement import krippendorff_alpha  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRIB = ROOT / "annotation" / "calibration" / "tribunal"
VOTOS, HUMANO = TRIB / "votos.jsonl", TRIB / "humano.json"
JUECES = ("opus", "sonnet", "haiku")
DUD, NO_FRAME = "dud", "sin_encuadre"


def cargar() -> dict[str, dict[str, str]]:
    """{id: {juez: clase}}. El voto más reciente de cada juez manda."""
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    if not VOTOS.exists():
        return {}
    for linea in VOTOS.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except json.JSONDecodeError:
            continue
        out[r["id"]][r.get("judge", "?")] = r.get("dominant") or DUD
    return out


def consenso(votos: dict[str, str]) -> tuple[str, str]:
    """(etiqueta, estado). El `dud` no cuenta para la mayoría pero sí se ve."""
    validos = [c for c in votos.values() if c != DUD]
    if not validos:
        return DUD, "SIN_VEREDICTO"
    conteo = collections.Counter(validos)
    top, n = conteo.most_common(1)[0]
    if n == len(votos) and len(votos) >= 2:
        return top, "UNANIME"
    if n > len(validos) / 2:
        return top, "MAYORIA"
    return top, "DISCREPANCIA"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-jueces", type=int, default=2,
                    help="Mínimo de votos para incluir el artículo (default 2)")
    args = ap.parse_args()

    datos = cargar()
    if not datos:
        raise SystemExit("✗ Todavía no hay votos.")

    cob = collections.Counter(j for v in datos.values() for j in v)
    print(f"  Artículos tocados: {len(datos):,}")
    print("  Cobertura: " + " · ".join(f"{j}={cob.get(j,0):,}" for j in JUECES))

    completos = {i: v for i, v in datos.items() if len(v) >= args.min_jueces}
    print(f"  Con ≥{args.min_jueces} jueces: {len(completos):,}")
    if not completos:
        return

    res = {i: consenso(v) for i, v in completos.items()}

    print("\n  Estado del consenso")
    est = collections.Counter(s for _, s in res.values())
    for s, n in est.most_common():
        print(f"    {s:<14} {n:5}  {n/len(res):6.1%}")

    clases = sorted({c for v in completos.values() for c in v.values()}
                    | {c for c, _ in res.values()})
    w = max(len(c) for c in clases)
    print(f"\n  Distribución\n    {'':<{w}}" + "".join(f"{j:>10}" for j in JUECES) + f"{'CONSENSO':>11}")
    dist = {j: collections.Counter(v[j] for v in completos.values() if j in v) for j in JUECES}
    cons = collections.Counter(c for c, _ in res.values())
    for c in sorted(clases, key=lambda c: -cons[c]):
        fila = "".join(f"{dist[j][c]:>10}" for j in JUECES)
        print(f"    {c:<{w}}{fila}{cons[c]:>11}")

    print("\n  Acuerdo entre modelos (α nominal, pares)")
    for a, b in itertools.combinations(JUECES, 2):
        u = [[v[a], v[b]] for v in completos.values() if a in v and b in v]
        al = krippendorff_alpha(u)
        print(f"    {a:>7} ↔ {b:<7} n={len(u):5}  α={al:+.3f}" if al is not None
              else f"    {a} ↔ {b}: sin datos")
    trio = [list(v.values()) for v in completos.values() if len(v) == 3]
    if trio:
        al = krippendorff_alpha(trio)
        print(f"    los tres      n={len(trio):5}  α={al:+.3f}")

    # Dirección del desacuerdo. El hallazgo de la corrida: el tribunal no
    # discute QUÉ encuadre tiene un texto, sino SI lo tiene. Esta tabla separa
    # las dos cosas, porque implican codebooks v1.2 muy distintos.
    trio_ids = [i for i, v in completos.items() if len(v) == 3]
    if trio_ids:
        solo = collections.Counter()
        tipo = collections.Counter()
        for i in trio_ids:
            v = completos[i]
            cnt = collections.Counter(v.values())
            raros = [j for j in v if cnt[v[j]] == 1]
            if len(raros) != 1:
                continue
            j = raros[0]
            otros = {c for k, c in v.items() if k != j}
            solo[j] += 1
            suyo, resto = v[j], next(iter(otros))
            if suyo != NO_FRAME and resto == NO_FRAME:
                tipo["ve encuadre donde los otros no"] += 1
            elif suyo == NO_FRAME and resto != NO_FRAME:
                tipo["no ve encuadre donde los otros sí"] += 1
            else:
                tipo["discrepan en QUÉ encuadre"] += 1
        print(f"\n  Dirección del desacuerdo (n={len(trio_ids)} con los tres)")
        print("    Quién queda en minoría:")
        for j in JUECES:
            print(f"      {j:<8} {solo.get(j, 0):4}")
        print("    De qué tipo es:")
        for t, n in tipo.most_common():
            print(f"      {t:<34} {n:4}  {n/max(1,sum(tipo.values())):6.1%}")

    if not HUMANO.exists():
        return
    humano = json.loads(HUMANO.read_text(encoding="utf-8"))
    pares = {i: res[i][0] for i in res if i in humano}
    if not pares:
        print("\n  Todavía no se ha tocado ningún artículo con etiqueta humana.")
        return

    ok = sum(1 for i, c in pares.items() if c == humano[i])
    al = krippendorff_alpha([[humano[i], c] for i, c in pares.items()])
    print(f"\n  Contra el humano (v1.0) — n={len(pares)}")
    print(f"    acuerdo bruto {ok/len(pares):.1%}" +
          (f"   α={al:+.3f}" if al is not None else ""))

    inst = {i: c for i, c in pares.items() if humano[i] == "institucionalismo"}
    if inst:
        print(f"\n    Los {len(inst)} que el humano llamó institucionalismo:")
        for c, n in collections.Counter(inst.values()).most_common():
            print(f"      {c:<{w}} {n:5}  {n/len(inst):6.1%}")
    otros = {i: c for i, c in pares.items() if humano[i] != "institucionalismo"}
    if otros:
        ok2 = sum(1 for i, c in otros.items() if c == humano[i])
        print(f"\n    Control (humano ≠ institucionalismo): "
              f"{ok2}/{len(otros)} = {ok2/len(otros):.1%}")


if __name__ == "__main__":
    main()
