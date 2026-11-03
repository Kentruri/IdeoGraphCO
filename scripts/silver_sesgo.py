#!/usr/bin/env python3
"""¿El silver enseña el ENCUADRE, o el medio y el año que lo publicaron?

Un clasificador puede acertar en validación por atajos que no sobreviven al
test: si una clase sale casi toda de un medio, aprende el estilo de ese medio;
si sale casi toda de un periodo, aprende los nombres y temas de ese periodo.
Este script mide los dos atajos sobre el silver entrenable (la misma regla que
`silver_estado.py --build`, con o sin el tope por medio):

  concentración   por clase: medios, cuota del 1º y de los 3 primeros, número
                  efectivo de medios (1/HHI) y ejemplos de 2026
  asociación      V de Cramér medio×clase; macro-F1 de predecir con SOLO el medio
  medio no visto  TF-IDF+LR con 5 folds aleatorios vs. agrupados por medio: la
                  caída mide cuánto depende del medio; por medio, el acierto de
                  sus artículos cuando el medio no estuvo en el entrenamiento
  año no visto    entrenado sin 2026 vs. con años mezclados (mismo tamaño),
                  evaluado en 2026: el gold (test) es 44 % de 2026

TF-IDF es un sustituto barato de los encoders: si él no depende del medio, no
prueba que un transformer no lo haga, pero si él sí depende, el problema está
en los datos y no en el modelo.

    python scripts/silver_sesgo.py                       # silver tal cual
    python scripts/silver_sesgo.py --tope-medio 0.10 --tope-medio-escasas 0.15
    python scripts/silver_sesgo.py --rapido              # sin los modelos (segundos)
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402

import silver_estado as S  # noqa: E402
from silver_mine import _doc  # noqa: E402

ROOT = S.ROOT
OUT = S.SILVER / "sesgo"


def concentracion(filas, y, src, anios) -> dict:
    out = {}
    for c in sorted(set(y)):
        cnt = collections.Counter(s for s, k in zip(src, y) if k == c)
        n = sum(cnt.values())
        top = cnt.most_common(3)
        out[c] = {"n": n, "medios": len(cnt), "top1": top[0][1] / n, "medio_top": top[0][0],
                  "top3": sum(v for _, v in top) / n,
                  "n_efectivo": 1 / sum((v / n) ** 2 for v in cnt.values()),
                  "n_2026": int(sum(1 for k, a in zip(y, anios) if k == c and a == 2026))}
    return out


def cramer_v(y, src) -> float:
    N, prior = len(y), collections.Counter(y)
    tab: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for s, c in zip(src, y):
        tab[s][c] += 1
    chi = sum((cnt.get(c, 0) - sum(cnt.values()) * prior[c] / N) ** 2
              / (sum(cnt.values()) * prior[c] / N)
              for cnt in tab.values() for c in prior)
    return math.sqrt(chi / (N * (len(prior) - 1)))


def _tfidf_pred(docs, Y, tr, te):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    vec = TfidfVectorizer(ngram_range=(1, 2), max_features=200_000, min_df=3, max_df=0.5,
                          sublinear_tf=True)
    clf = LogisticRegression(C=8.0, max_iter=2000, class_weight="balanced")
    clf.fit(vec.fit_transform([docs[i] for i in tr]), Y[tr])
    return clf.predict(vec.transform([docs[i] for i in te]))


def modelos(docs, Y, G, A, clases) -> dict:
    from sklearn.metrics import f1_score
    from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

    N = len(Y)
    res: dict = {}
    # medio solo: clase mayoritaria del medio en los folds de entrenamiento
    pred = np.zeros(N, dtype=int)
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(docs, Y):
        cnt: dict = collections.defaultdict(collections.Counter)
        for i in tr:
            cnt[G[i]][Y[i]] += 1
        glob = collections.Counter(Y[tr]).most_common(1)[0][0]
        for i in te:
            pred[i] = cnt[G[i]].most_common(1)[0][0] if G[i] in cnt else glob
    res["solo_medio_f1"] = float(f1_score(Y, pred, average="macro"))

    oof = {}
    for nombre, sp, grupos in (("aleatorio", StratifiedKFold(5, shuffle=True, random_state=0), None),
                               ("medio_no_visto", StratifiedGroupKFold(5, shuffle=True, random_state=0), G)):
        p = np.zeros(N, dtype=int)
        for tr, te in sp.split(docs, Y, grupos):
            p[te] = _tfidf_pred(docs, Y, tr, te)
        oof[nombre] = p
        res[f"tfidf_{nombre}_f1"] = float(f1_score(Y, p, average="macro"))
        res[f"tfidf_{nombre}_por_clase"] = dict(zip(clases, map(float, f1_score(Y, p, average=None))))
        print(f"    TF-IDF {nombre:<16} macro-F1 {res[f'tfidf_{nombre}_f1']:.3f}", flush=True)

    # por medio: acierto con el medio en el entrenamiento vs. sin él
    por_medio = {}
    for s in {g for g, n in collections.Counter(G).items() if n >= 60}:
        m = G == s
        por_medio[s] = {"n": int(m.sum()),
                        "acierto_visto": float((oof["aleatorio"][m] == Y[m]).mean()),
                        "acierto_no_visto": float((oof["medio_no_visto"][m] == Y[m]).mean())}
    res["por_medio"] = por_medio

    # año: entrenar sin 2026 vs. con años mezclados del mismo tamaño; evaluar en
    # la mitad de 2026 que ninguno de los dos vio
    rng = np.random.default_rng(0)
    d26 = np.where(A == 2026)[0]
    ev = rng.choice(d26, len(d26) // 2, replace=False)
    sin26 = np.where(A != 2026)[0]
    mezcla = rng.choice(np.setdiff1d(np.arange(N), ev), len(sin26), replace=False)
    for nombre, tr in (("sin_2026", sin26), ("anios_mezclados", mezcla)):
        p = _tfidf_pred(docs, Y, tr, ev)
        res[f"anio_{nombre}_f1"] = float(f1_score(Y[ev], p, average="macro"))
        res[f"anio_{nombre}_por_clase"] = dict(zip(clases, map(float, f1_score(Y[ev], p, average=None,
                                                                                labels=range(len(clases))))))
        print(f"    TF-IDF {nombre:<16} en 2026: macro-F1 {res[f'anio_{nombre}_f1']:.3f}", flush=True)
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tope-medio", type=float, default=0.0)
    ap.add_argument("--tope-medio-escasas", type=float, default=0.0)
    ap.add_argument("--rapido", action="store_true", help="solo concentración y asociación")
    ap.add_argument("--etiqueta", default="", help="nombre para el JSON de salida")
    args = ap.parse_args()

    E = S.todas()
    filas, _ = S.entrenables(E)
    filas, recortados = S.aplica_topes(filas, args.tope_medio, args.tope_medio_escasas)
    y = [e.clase for _, e in filas]
    src = [a.get("source") or "?" for a, _ in filas]
    anios = [S.anio(a) for a, _ in filas]
    gold = set(json.loads((ROOT / "annotation" / "gold_set_v2_ids.json").read_text()))
    gold_anios = collections.Counter(S.anio(a) for a in S.iter_raw() if a["id"] in gold)

    res = {"medido": time.strftime("%Y-%m-%d %H:%M"), "n": len(filas),
           "tope_medio": args.tope_medio, "tope_medio_escasas": args.tope_medio_escasas,
           "recortados": sum(recortados.values()),
           "concentracion": concentracion(filas, y, src, anios),
           "cramer_v": cramer_v(y, src),
           "gold_2026": gold_anios[2026] / sum(gold_anios.values())}
    print(f"  {len(filas):,} entrenables · recortados por tope {res['recortados']:,} · "
          f"V de Cramér medio×clase {res['cramer_v']:.3f} · gold de 2026 {res['gold_2026']:.0%}")
    print(f"  {'clase':<18}{'n':>6}{'medios':>8}{'top1':>6}{'top3':>6}{'n_ef':>6}{'2026':>7}  medio top")
    for c, r in res["concentracion"].items():
        print(f"  {c:<18}{r['n']:>6}{r['medios']:>8}{r['top1']:>6.0%}{r['top3']:>6.0%}"
              f"{r['n_efectivo']:>6.1f}{r['n_2026'] / r['n']:>7.0%}  {r['medio_top']}")

    if not args.rapido:
        clases = sorted(set(y))
        Y = np.array([clases.index(c) for c in y])
        res["modelos"] = modelos([_doc(a) for a, _ in filas], Y, np.array(src), np.array(anios), clases)
        m = res["modelos"]
        print(f"\n  solo el medio: macro-F1 {m['solo_medio_f1']:.3f}")
        print(f"  {'clase':<18}{'aleat.':>8}{'medio⊄':>8}{'sin26':>8}{'mezcla':>8}")
        for c in clases:
            print(f"  {c:<18}{m['tfidf_aleatorio_por_clase'][c]:>8.3f}"
                  f"{m['tfidf_medio_no_visto_por_clase'][c]:>8.3f}"
                  f"{m['anio_sin_2026_por_clase'][c]:>8.3f}{m['anio_anios_mezclados_por_clase'][c]:>8.3f}")
        caidas = sorted(m["por_medio"].items(),
                        key=lambda kv: kv[1]["acierto_no_visto"] - kv[1]["acierto_visto"])
        print("\n  medios cuyo acierto más cae cuando no se vieron al entrenar:")
        for s, r in caidas[:10]:
            print(f"    {s:<24} n={r['n']:<5} visto {r['acierto_visto']:.2f} → no visto {r['acierto_no_visto']:.2f}")

    OUT.mkdir(parents=True, exist_ok=True)
    nombre = args.etiqueta or time.strftime("%Y%m%d_%H%M")
    (OUT / f"sesgo_{nombre}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    print(f"\n  ✓ {(OUT / f'sesgo_{nombre}.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
