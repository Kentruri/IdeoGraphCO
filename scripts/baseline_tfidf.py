"""Línea base del benchmark: TF-IDF + regresión logística.

Es la referencia mínima del P2.1: un encoder que no la supere con claridad no
justifica su coste. Para que la comparación sea justa usa lo mismo que los
transformers:

- la entrada canónica (`build_model_input`: titular limpio + cuerpo),
- el mismo split por ID (`data/processed/splits*.json`),
- los mismos pesos por clase (`sqrt_inverse` sobre la distribución de train),
- la selección en VALIDACIÓN (el test/gold no se toca).

Escribe `logs/benchmark/[<tag>/]tfidf__seed<N>/metrics.json` con el formato
de `src.training.train`, así `compare_models.py` la pone en la misma tabla.

Uso:
    python scripts/baseline_tfidf.py --tag cribado \\
        --splits data/processed/splits_cribado.json
"""

import argparse
import json
import time
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from src.core.paths import LOGS_DIR, PROCESSED_DIR
from src.core.schema import IDEOLOGY_CLASSES
from src.core.text import build_model_input
from src.training.class_weights import class_weights
from src.training.data.dataset import resolve_label_idx


def scores(y_true: list[int], y_pred: list[int]) -> dict[str, float]:
    p, r, f, _ = precision_recall_fscore_support(
        y_true, y_pred, labels=range(len(IDEOLOGY_CLASSES)), average="macro", zero_division=0,
    )
    return {"val/f1_macro": f, "val/precision_macro": p, "val/recall_macro": r,
            "val/accuracy": accuracy_score(y_true, y_pred)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dataset", default=str(PROCESSED_DIR / "dataset.jsonl"))
    ap.add_argument("--splits", default=str(PROCESSED_DIR / "splits.json"))
    ap.add_argument("--tag", default=None, help="Carpeta de la tanda en logs/benchmark/")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--weights", default="sqrt_inverse", help="Modo de pesos por clase")
    args = ap.parse_args()

    splits = json.loads(Path(args.splits).read_text(encoding="utf-8"))
    wanted = set(splits["train"]) | set(splits["val"])
    by_id = {}
    with open(args.dataset, encoding="utf-8") as f:
        for line in f:
            record = json.loads(line)
            if record["id"] in wanted:
                by_id[record["id"]] = record

    def xy(ids: list[str]) -> tuple[list[str], list[int]]:
        records = [by_id[i] for i in ids]
        return ([build_model_input(r.get("title"), r.get("text", "")) for r in records],
                [resolve_label_idx(r) for r in records])

    x_train, y_train = xy(splits["train"])
    x_val, y_val = xy(splits["val"])
    counts = [y_train.count(i) for i in range(len(IDEOLOGY_CLASSES))]
    weights = class_weights(counts, args.weights)

    start = time.time()
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2,
                                 max_features=200_000)
    clf = LogisticRegression(C=5.0, max_iter=3000, random_state=args.seed,
                             class_weight=dict(enumerate(weights)))
    clf.fit(vectorizer.fit_transform(x_train), y_train)
    duration = time.time() - start
    y_pred = clf.predict(vectorizer.transform(x_val)).tolist()

    p, r, f, support = precision_recall_fscore_support(
        y_val, y_pred, labels=range(len(IDEOLOGY_CLASSES)), zero_division=0,
    )
    per_class = {
        cls: {"precision": round(float(p[i]), 4), "recall": round(float(r[i]), 4),
              "f1": round(float(f[i]), 4), "support": int(support[i])}
        for i, cls in enumerate(IDEOLOGY_CLASSES)
    }
    # Sesgo temporal: el gold es 44 % de 2026, el train bastante menos.
    idx_2026 = [i for i, aid in enumerate(splits["val"])
                if (by_id[aid].get("date") or "").startswith("2026")]
    val_2026 = scores([y_val[i] for i in idx_2026], [y_pred[i] for i in idx_2026])

    run_key = f"tfidf__seed{args.seed}"
    out_dir = LOGS_DIR / "benchmark" / (f"{args.tag}/{run_key}" if args.tag else run_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    val_metrics = scores(y_val, y_pred)
    metrics = {
        "encoder_alias": run_key,
        "model_name": "tfidf+logreg",
        "seed": args.seed,
        "train_duration_seconds": duration,
        "monitored_metric": "val/f1_macro",
        "best_val_score": val_metrics["val/f1_macro"],
        "ran_test": False,
        "val_metrics": val_metrics,
        "val_per_class": per_class,
        "val_confusion_matrix": confusion_matrix(
            y_val, y_pred, labels=range(len(IDEOLOGY_CLASSES))).tolist(),
        "val_2026": {"n": len(idx_2026), **val_2026},
        "class_names": IDEOLOGY_CLASSES,
        "config": {"splits": args.splits, "train": len(x_train), "val": len(x_val),
                   "class_weights": weights, "C": 5.0, "ngram_range": [1, 2]},
    }
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"TF-IDF + LR · train {len(x_train):,} · val {len(x_val):,} · {duration:.0f} s")
    print(f"  macro-F1 val {val_metrics['val/f1_macro']:.3f}   "
          f"en 2026 (n={len(idx_2026)}) {val_2026['val/f1_macro']:.3f}")
    for cls, m in per_class.items():
        print(f"    {cls:<18} F1 {m['f1']:.3f}  (n={m['support']})")
    print(f"  ✓ {out_dir / 'metrics.json'}")


if __name__ == "__main__":
    main()
