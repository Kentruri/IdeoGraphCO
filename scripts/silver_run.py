#!/usr/bin/env python3
"""Etiqueta el silver con Gemini sobre el plan de muestreo dirigido.

El plan (scripts/silver_sample.py) ya excluye el gold y trae candidatos por
clase, así que el conjunto resultante está balanceado para ENTRENAR. La
prevalencia real del corpus se estima aparte con el estrato `_aleatorio` y con
el gold, que sí es una muestra aleatoria.

Reanudable: relee los votos ya escritos y sigue por donde iba.

    python scripts/silver_run.py --max 40          # medir coste
    python scripts/silver_run.py                   # todo el plan
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from src.agents.silver.codebook import build_system_prompt  # noqa: E402
from src.agents.silver.judges import build_judges  # noqa: E402
from src.agents.silver.verdicts import append_verdict, judged_ids  # noqa: E402
from src.core.paths import RAW_DIR, ROOT  # noqa: E402
from scripts.silver_agent import _sin_medio  # noqa: E402

PLAN = ROOT / "data" / "silver" / "plan_muestreo.json"
VOTOS = ROOT / "data" / "silver" / "verdicts.jsonl"
SIN_RECORTE = 400_000


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--judge", default="gemini")
    ap.add_argument("--votos", default=None, help="almacén alternativo (para pruebas)")
    ap.add_argument("--max", type=int, default=None)
    ap.add_argument("--input", default=None)
    ap.add_argument("--corregir", action="store_true",
                    help="añade el aviso del sesgo medido al final del prompt")
    args = ap.parse_args()

    plan = json.loads(PLAN.read_text(encoding="utf-8"))["plan"]
    # Intercalado por clase: si la corrida se corta, lo hecho sigue balanceado
    # en vez de tener las primeras clases completas y las últimas vacías.
    colas = {c: list(ids) for c, ids in plan.items()}
    orden: list[tuple[str, str]] = []
    while any(colas.values()):
        for c in list(colas):
            if colas[c]:
                orden.append((c, colas[c].pop(0)))

    global VOTOS
    if args.votos:
        VOTOS = Path(args.votos)
    ya = judged_ids(VOTOS, judge=args.judge)
    pend = [(c, i) for c, i in orden if i not in ya]
    if args.max:
        pend = pend[: args.max]
    print(f"  Plan: {len(orden):,} · ya votados: {len(ya):,} · en esta corrida: {len(pend):,}")
    if not pend:
        return

    quiero = {i for _, i in pend}
    entrada = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    arts = {}
    with entrada.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            a = json.loads(linea)
            if a.get("id") in quiero:
                arts[a["id"]] = a

    sistema = build_system_prompt(include_examples=True)
    if args.corregir:
        # Medido: sobre artículos aleatorios Gemini manda el 46,9 % a
        # institucionalismo, frente al 8,6 % del consenso de tres jueces de
        # Claude. La corrección va al FINAL, que es lo último que lee.
        sistema += (
            "\n\n## AVISO FINAL — SESGO MEDIDO EN TI\n\n"
            "Se ha medido que asignas `institucionalismo` al 47 % de los "
            "artículos, cuando el consenso de tres anotadores independientes "
            "sobre el mismo tipo de corpus da 9 %. Estás tomando el "
            "vocabulario de la administración pública por un encuadre.\n\n"
            "Antes de responder `institucionalismo`, comprueba que el texto "
            "ARGUMENTA que el procedimiento importa. Que una entidad sea el "
            "sujeto de la noticia, que se cite una norma o que el tono sea "
            "formal NO basta: eso es `sin_encuadre`.\n\n"
            "El mismo consenso da 55 % de `sin_encuadre` en corpus aleatorio. "
            "Si tu respuesta casi nunca es `sin_encuadre`, estás forzando "
            "etiquetas.")
    juez = build_judges([args.judge], sistema)[0]
    juez.max_chars = SIN_RECORTE

    conteo: collections.Counter = collections.Counter()
    t0 = time.monotonic()
    for n, (estrato, aid) in enumerate(pend, 1):
        a = arts.get(aid)
        if a is None:
            conteo["no_estaba"] += 1
            continue
        v = juez.judge(_sin_medio(a.get("title") or ""), a["text"])
        if not v.ok:
            conteo["fallo"] += 1
            if v.quota:
                print(f"  ✗ Cuota agotada en {n}. Lo hecho queda guardado.")
                break
            continue
        append_verdict(VOTOS, aid, v)
        conteo[v.dominant] += 1
        if n % 20 == 0 or n == len(pend):
            seg = time.monotonic() - t0
            print(f"  [{n}/{len(pend)}] {seg/n:.1f}s/art · faltan ~{(len(pend)-n)*seg/n/60:.0f} min")

    print("\n  Reparto de esta corrida:")
    for c, k in conteo.most_common():
        print(f"    {c:<20} {k:5}")
    print(f"\n  → {VOTOS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
