#!/usr/bin/env python3
"""Gemini desempata los artículos donde el tribunal de tres no llegó a consenso.

Un artículo sin consenso es aquel en el que los tres jueces dijeron cosas
distintas: no hay mayoría, así que no hay etiqueta. Gemini vota como cuarto
juez y su voto rompe el empate, quedando registrado como un voto más —no como
autoridad— en el mismo almacén.

    python scripts/tribunal_desempate.py [--dry-run] [--max N]
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.agents.silver.codebook import build_system_prompt  # noqa: E402
from src.agents.silver.judges import build_judges  # noqa: E402
from src.agents.silver.verdicts import append_verdict  # noqa: E402
from scripts.silver_agent import _sin_medio  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TRIB = ROOT / "annotation" / "calibration" / "tribunal"
VOTOS, CORPUS = TRIB / "votos.jsonl", TRIB / "corpus.jsonl"
DUD = "dud"
# Nada de recortar: los jueces de Claude vieron el artículo entero y el voto
# de desempate tiene que compararse con lo mismo.
SIN_RECORTE = 400_000


def votos_por_articulo() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for linea in VOTOS.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        r = json.loads(linea)
        out[r["id"]][r.get("judge", "?")] = r.get("dominant") or DUD
    return out


NO_FRAME = "sin_encuadre"


def sin_consenso(votos: dict[str, dict[str, str]], modo: str) -> list[str]:
    """Artículos que piden un cuarto voto.

    `discrepancia`: los tres dijeron cosas distintas, no hay mayoría.
    `mixto`: discrepan sobre si HAY encuadre. Es la banda donde se midió que
        vive todo el déficit de α (α=-0.02 ahí frente a +0.83 donde los tres
        ven encuadre), así que es donde un voto más aporta algo.
    """
    pendientes = []
    for aid, v in votos.items():
        propios = {j: c for j, c in v.items() if j in ("opus", "sonnet", "haiku")}
        if len(propios) < 3 or "gemini" in v:
            continue
        if modo == "mixto":
            marcos = {c == NO_FRAME for c in propios.values()}
            if len(marcos) > 1:
                pendientes.append(aid)
            continue
        validos = [c for c in propios.values() if c != DUD]
        if not validos:
            pendientes.append(aid)
            continue
        top, n = collections.Counter(validos).most_common(1)[0]
        if n <= len(validos) / 2:
            pendientes.append(aid)
    return sorted(pendientes)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--judge", default="gemini")
    ap.add_argument("--modo", choices=["discrepancia", "mixto"], default="discrepancia",
                    help="qué artículos mandar: sin mayoría, o la banda ambigua")
    args = ap.parse_args()

    votos = votos_por_articulo()
    pendientes = sin_consenso(votos, args.modo)
    if args.max:
        pendientes = pendientes[: args.max]

    print(f"  Pendientes ({args.modo}): {len(pendientes)}")
    if not pendientes:
        return
    for aid in pendientes[:8]:
        print(f"    {aid[:10]}  " + " · ".join(
            f"{j}={votos[aid][j]}" for j in ("opus", "sonnet", "haiku")))
    if args.dry_run:
        print("\n  (dry-run: no se llamó a Gemini)")
        return

    gold = {a["id"]: a for a in (json.loads(x) for x in
            CORPUS.read_text(encoding="utf-8").splitlines() if x.strip())}
    juez = build_judges([args.judge], build_system_prompt(include_examples=True))[0]
    juez.max_chars = SIN_RECORTE

    conteo: collections.Counter = collections.Counter()
    for i, aid in enumerate(pendientes, 1):
        art = gold.get(aid)
        if art is None:
            print(f"  [{i}/{len(pendientes)}] {aid[:10]} — no está en el corpus")
            continue
        v = juez.judge(_sin_medio(art.get("title") or ""), art["text"])
        if not v.ok:
            print(f"  [{i}/{len(pendientes)}] {aid[:10]} ✗ {v.error}")
            conteo["fallo"] += 1
            if v.quota:
                print("  ✗ Cuota de Gemini agotada: paro aquí.")
                break
            continue
        append_verdict(VOTOS, aid, v)
        conteo[v.dominant] += 1
        otros = " · ".join(f"{j}={votos[aid][j][:4]}" for j in ("opus", "sonnet", "haiku"))
        print(f"  [{i}/{len(pendientes)}] {aid[:10]}  {otros}  → gemini={v.dominant}")

    print("\n  Voto de desempate:")
    for c, n in conteo.most_common():
        print(f"    {c:<20} {n}")


if __name__ == "__main__":
    main()
