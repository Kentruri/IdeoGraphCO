#!/usr/bin/env python3
"""Compara el acuerdo entre jueces ANTES y DESPUÉS de la regla de umbral.

La hipótesis que se prueba: si el 79 % del desacuerdo era sobre *si hay*
encuadre y no sobre *cuál*, entonces operacionalizar ese umbral debería subir
α. Si no sube, la hipótesis era falsa y la regla sobra.

Los mismos 150 artículos, los mismos tres jueces, a ciegas de su voto previo.
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

TRIB = Path(__file__).resolve().parent.parent / "annotation" / "calibration" / "tribunal"
JUECES = ("opus", "sonnet", "haiku")
NO_FRAME = "sin_encuadre"


def cargar_nuevo(exp: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    f = next((x for x in (exp / "votos.jsonl", exp / "votos_v12.jsonl") if x.exists()), None)
    if f is None:
        return {}
    for linea in f.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            r = json.loads(linea)
            out[r["id"]][r.get("judge", "?")] = r.get("dominant") or "dud"
    return out


def direccion(votos: dict[str, dict[str, str]], ids: list[str]) -> collections.Counter:
    tipo: collections.Counter = collections.Counter()
    for i in ids:
        v = votos[i]
        cnt = collections.Counter(v.values())
        raros = [j for j in v if cnt[v[j]] == 1]
        if len(raros) != 1:
            continue
        suyo = v[raros[0]]
        resto = next(c for j, c in v.items() if j != raros[0])
        if suyo != NO_FRAME and resto == NO_FRAME:
            tipo["ve encuadre donde los otros no"] += 1
        elif suyo == NO_FRAME and resto != NO_FRAME:
            tipo["no ve encuadre donde los otros sí"] += 1
        else:
            tipo["discrepan en QUÉ encuadre"] += 1
    return tipo


def resumen(votos: dict[str, dict[str, str]], ids: list[str], etiqueta: str) -> dict:
    trio = [[votos[i][j] for j in JUECES] for i in ids]
    alfa = krippendorff_alpha(trio)
    unan = sum(1 for u in trio if len(set(u)) == 1)
    print(f"\n  {etiqueta}  (n={len(ids)})")
    print(f"    α             {alfa:+.3f}")
    print(f"    unánimes      {unan:4}  {unan/len(ids):6.1%}")
    for a, b in itertools.combinations(JUECES, 2):
        pa = krippendorff_alpha([[votos[i][a], votos[i][b]] for i in ids])
        print(f"    {a:>6} ↔ {b:<7} {pa:+.3f}")
    return {"alpha": alfa, "unanimes": unan, "trio": trio}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="experimento_umbral",
                    help="carpeta de la iteración bajo annotation/calibration/tribunal/")
    ap.add_argument("--etiqueta", default="DESPUÉS")
    args = ap.parse_args()
    exp = TRIB / args.dir
    meta = json.loads((exp / "muestra.json").read_text(encoding="utf-8"))
    base_votos = {i: v for i, v in meta["baseline"]["votos"].items()}
    v12 = cargar_nuevo(exp)

    ids = sorted(i for i in meta["ids"]
                 if all(j in v12.get(i, {}) for j in JUECES))
    print(f"  Re-juzgados por los tres: {len(ids)} de {meta['n']}")
    if not ids:
        raise SystemExit("  (todavía no hay suficientes votos nuevos)")

    a = resumen(base_votos, ids, "ANTES — codebook v1.1")
    b = resumen(v12, ids, f"DESPUÉS — {args.etiqueta}")

    d = b["alpha"] - a["alpha"]
    print(f"\n  ΔΑ = {d:+.3f}   " + (
        "la regla AUMENTA el acuerdo" if d > 0.02 else
        "la regla REDUCE el acuerdo" if d < -0.02 else
        "sin efecto medible"))

    print("\n  Dirección del desacuerdo")
    da, db = direccion(base_votos, ids), direccion(v12, ids)
    claves = sorted(set(da) | set(db))
    w = max(len(c) for c in claves)
    print(f"    {'':<{w}}  antes  después")
    for c in claves:
        print(f"    {c:<{w}}  {da[c]:5}  {db[c]:7}")

    print("\n  Distribución del consenso")
    def cons(votos):
        out = collections.Counter()
        for i in ids:
            vals = [votos[i][j] for j in JUECES]
            out[collections.Counter(vals).most_common(1)[0][0]] += 1
        return out
    ca, cb = cons(base_votos), cons(v12)
    for c in sorted(set(ca) | set(cb), key=lambda c: -(ca[c] + cb[c])):
        print(f"    {c:<20} {ca[c]:5} → {cb[c]:5}  ({cb[c]-ca[c]:+d})")

    # Medición DIRIGIDA. Un cambio que toca el 1 % de los votos no se ve en α
    # sobre 150 artículos: queda por debajo del ruido. Pero sí se ve si se mide
    # solo donde el cambio podía morder — los artículos que algún juez movió.
    tocados = [i for i in ids
               if any(base_votos[i][j] != v12[i][j] for j in JUECES)]
    if tocados:
        print(f"\n  Solo donde algún juez cambió de voto (n={len(tocados)})")
        for votos, etq in ((base_votos, "antes  "), (v12, "después")):
            trio = [[votos[i][j] for j in JUECES] for i in tocados]
            al = krippendorff_alpha(trio)
            u = sum(1 for t in trio if len(set(t)) == 1)
            print(f"    {etq}  α={al:+.3f}  unánimes {u:3}/{len(trio)} = {u/len(trio):5.1%}")

    estables = [i for i in ids if i not in set(tocados)]
    if estables:
        trio = [[v12[i][j] for j in JUECES] for i in estables]
        u = sum(1 for t in trio if len(set(t)) == 1)
        print(f"\n  Donde nadie cambió (n={len(estables)}): unánimes {u/len(trio):.1%}")

    cambios = sum(1 for i in ids for j in JUECES if base_votos[i][j] != v12[i][j])
    print(f"\n  Votos individuales que cambiaron: {cambios} de {len(ids)*3} "
          f"({cambios/(len(ids)*3):.1%})")


if __name__ == "__main__":
    main()
