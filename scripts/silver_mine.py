#!/usr/bin/env python3
"""Mina candidatos de las clases escasas con un clasificador de criba.

El plan dirigido (`silver_sample.py`) puntuaba con los marcadores léxicos del
codebook y acertaba poco justo donde más falta hacía: de cada 900 candidatos,
los jueces confirmaron 86 de populismo, 86 de doctrinarismo y 154 de
personalismo. Con 6.500 etiquetas ya puestas hay algo mejor que el léxico: un
clasificador TF-IDF + regresión logística entrenado con ellas. No gasta cuota
—corre en local en un par de minutos— y solo ORDENA el corpus; la etiqueta la
siguen poniendo los tres jueces.

Medido con validación cruzada a 5 pliegues sobre el estrato aleatorio del plan
(prevalencia natural), su top 1 % acierta ~50 % en populismo y ~60 % en
personalismo, frente al ~10-17 % del léxico.

Sesgo que introduce, y por qué se acepta: prioriza textos parecidos a los ya
etiquetados. Se compensa con un tope por fuente (que ningún medio acapare una
clase) y no toca la etiqueta, solo qué artículos se juzgan.

    python scripts/silver_mine.py --cuotas personalismo=1200,populismo=1300 \
        --out data/silver/plan_r4.json
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import silver_estado as S  # noqa: E402

ROOT = S.ROOT
RAW = ROOT / "data" / "raw" / "articles.jsonl"
GOLD_IDS = ROOT / "annotation" / "gold_set_v2_ids.json"


def _doc(a: dict) -> str:
    # El titular dos veces: es donde el codebook dice que el texto declara su marco.
    t = a.get("title") or ""
    return f"{t} {t} " + (a.get("text") or "")[:6000]


def _titulo_norm(t: str) -> str:
    t = unicodedata.normalize("NFD", (t or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).split("|")[0].strip()[:90]


def entrena_criba(raw: dict[str, dict], E: dict, C: float = 8.0):
    """TF-IDF + regresión logística sobre las etiquetas resueltas del silver.

    Aprende también `sin_encuadre`: así un texto sin encuadre no se cuela
    como candidato solo porque comparte vocabulario con una clase.
    Devuelve (vectorizador, clasificador, ids de entrenamiento, etiquetas).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    etiq = {i: e.clase for i, e in E.items()
            if i in raw and e.estado not in (S.PENDIENTE, S.DISCREPANCIA)
            and (e.clase in S.CLASES or e.clase == S.NF)}
    ids_tr = sorted(etiq)
    y = np.array([etiq[i] for i in ids_tr])
    vec = TfidfVectorizer(sublinear_tf=True, min_df=3, max_df=0.5,
                          ngram_range=(1, 2), max_features=300_000)
    X = vec.fit_transform([_doc(raw[i]) for i in ids_tr])
    clf = LogisticRegression(C=C, max_iter=2000, class_weight="balanced")
    clf.fit(X, y)
    return vec, clf, ids_tr, y


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cuotas", required=True,
                    help="clase=n,... candidatos por clase (las escasas primero)")
    ap.add_argument("--tope-fuente", type=float, default=0.08,
                    help="fracción máxima de los candidatos de una clase que puede venir de un medio")
    ap.add_argument("--C", type=float, default=8.0)
    ap.add_argument("--out", default="data/silver/plan_r4.json")
    ap.add_argument("--excluir-meta", default=None,
                    help="r4_meta.json de una ronda en curso: sus artículos aún sin votos "
                         "no están en el estado y volverían a salir")
    args = ap.parse_args()

    cuotas = {k: int(v) for k, v in (x.split("=") for x in args.cuotas.split(","))}
    for c in cuotas:
        if c not in S.CLASES:
            raise SystemExit(f"✗ clase desconocida: {c}")

    t0 = time.time()
    gold = set(json.loads(GOLD_IDS.read_text(encoding="utf-8")))
    raw = {}
    with RAW.open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                a = json.loads(linea)
                raw[a["id"]] = a

    E = S.todas()
    vec, clf, ids_tr, y = entrena_criba(raw, E, C=args.C)
    print(f"  entrenamiento de la criba: {len(ids_tr):,} artículos "
          f"({time.time() - t0:.0f}s)")
    for c, n in collections.Counter(y).most_common():
        print(f"    {c:<18}{n:6,}")

    # El pool: ni gold, ni nada que alguna ronda ya haya votado o tenga en cola.
    en_cola: set[str] = set()
    if args.excluir_meta:
        m = json.loads((ROOT / args.excluir_meta).read_text(encoding="utf-8"))
        en_cola = set(m.get("candidatos", [])) | set(m.get("confirmar", [])) | set(m.get("decidir_p3", []))
    pool = [i for i in raw if i not in gold and i not in E and i not in en_cola]
    print(f"\n  pool sin juzgar: {len(pool):,}")

    P = clf.predict_proba(vec.transform([_doc(raw[i]) for i in pool]))
    clases = list(clf.classes_)
    print(f"  criba entrenada y aplicada ({time.time() - t0:.0f}s)")

    # Ni casi-duplicados del gold ni de lo ya etiquetado: un titular repetido
    # (notas de agencia replicadas por varios medios) es la fuga más barata.
    vistos = {_titulo_norm(raw[i].get("title")) for i in gold | set(ids_tr) if i in raw}

    usados: set[str] = set()
    plan: dict[str, list[dict]] = {}
    # Las escasas eligen primero: si un artículo sirve a dos, va a la que menos tiene.
    for c in sorted(cuotas, key=lambda c: collections.Counter(y)[c]):
        k = clases.index(c)
        tope = max(20, int(cuotas[c] * args.tope_fuente))
        por_fuente: collections.Counter = collections.Counter()
        sel = []
        for j in np.argsort(-P[:, k]):
            aid = pool[j]
            if aid in usados:
                continue
            tn = _titulo_norm(raw[aid].get("title"))
            fuente = raw[aid].get("source") or "?"
            if tn in vistos or por_fuente[fuente] >= tope:
                continue
            sel.append({"id": aid, "p": round(float(P[j, k]), 4),
                        "argmax": clases[int(P[j].argmax())], "fuente": fuente})
            usados.add(aid)
            vistos.add(tn)
            por_fuente[fuente] += 1
            if len(sel) >= cuotas[c]:
                break
        plan[c] = sel
        p = [s["p"] for s in sel]
        print(f"    {c:<18}{len(sel):6,}  p∈[{min(p):.2f}, {max(p):.2f}]  "
              f"argmax propio {sum(s['argmax'] == c for s in sel) / len(sel):.0%}  "
              f"fuentes {len(por_fuente)}")

    out = ROOT / args.out
    out.write_text(json.dumps({
        "creado": time.strftime("%Y-%m-%d %H:%M"),
        "entrenamiento": dict(collections.Counter(y)),
        "pool": len(pool), "cuotas": cuotas, "tope_fuente": args.tope_fuente,
        "plan": plan,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  ✓ {sum(len(v) for v in plan.values()):,} candidatos → {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
