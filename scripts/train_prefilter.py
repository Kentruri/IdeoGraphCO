"""Entrena el prefilter local con las decisiones acumuladas del filter LLM.

Dataset: logs/filter_decisions.jsonl — cada línea con `text_head` (los
primeros ~3000 chars del artículo) y `kept` (decisión del LLM). Es el
paradigma teacher→student de la tesis aplicado al filtro: el LLM enseña,
el modelo local barato resuelve los casos obvios.

Calibración de umbrales sobre un split de validación:
- `hi`: menor umbral con precisión de KEEP ≥ --keep-precision (default 0.98)
- `lo`: mayor umbral con precisión de DROP ≥ --drop-precision (default 0.98)
El reporte imprime qué fracción del tráfico se resuelve sin LLM.

Uso:
    python scripts/train_prefilter.py
    python scripts/train_prefilter.py --min-samples 300 --keep-precision 0.99
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def load_decisions(log_path: Path) -> tuple[list[str], list[int]]:
    """Carga (texts, labels) de las decisiones del LLM que traen text_head."""
    texts: list[str] = []
    labels: list[int] = []
    seen_ids: set[str] = set()
    seen_texts: set[int] = set()
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            record = json.loads(line)
            # Solo decisiones del LLM (no re-aprender del propio prefilter)
            if record.get("engine", "llm") != "llm":
                continue
            text = record.get("text_head")
            if not text or len(text) < 200:
                continue
            record_id = record.get("id") or record.get("url")
            if record_id in seen_ids:
                continue
            # Dedup por contenido: los cables republicados (Colprensa/EFE)
            # entran con ids/URLs distintos; sin esto el mismo texto caía en
            # train Y val e inflaba el AUC y la calibración de umbrales.
            text_key = hash(text)
            if text_key in seen_texts:
                continue
            seen_ids.add(record_id)
            seen_texts.add(text_key)
            texts.append(text)
            labels.append(1 if record.get("kept") else 0)
    return texts, labels


def calibrate_thresholds(
    probs, labels, keep_precision: float, drop_precision: float,
) -> tuple[float, float]:
    """Busca (lo, hi) que cumplan las precisiones objetivo en validación."""
    import numpy as np

    probs = np.asarray(probs)
    labels = np.asarray(labels)

    # Un umbral solo es válido con soporte estadístico real en validación:
    # aceptar precisión=1.0 sobre 3 muestras producía umbrales de juguete.
    min_support = max(20, int(0.02 * len(probs)))

    hi = 1.01  # imposible: nunca hace keep directo si no se encuentra umbral
    for threshold in np.arange(0.50, 1.00, 0.01):
        mask = probs >= threshold
        if mask.sum() < min_support:
            break
        precision = labels[mask].mean()
        if precision >= keep_precision:
            hi = float(threshold)
            break

    lo = -0.01  # imposible: nunca dropea directo si no se encuentra umbral
    for threshold in np.arange(0.50, 0.00, -0.01):
        mask = probs <= threshold
        if mask.sum() < min_support:
            break
        precision = (1 - labels[mask]).mean()
        if precision >= drop_precision:
            lo = float(threshold)
            break

    # Garantizar zona gris mínima: con lo >= hi el LLM nunca volvería a
    # consultarse, el prefilter decidiría TODO con la calibración de un val
    # pequeño, y — peor — dejaría de generarse señal nueva para re-entrenarlo
    # (los logs del LLM son su dataset). Se empujan ambos umbrales de forma
    # simétrica para conservar keep y drop baratos en los extremos.
    min_gray = 0.10
    if hi <= 1.0 and lo >= 0.0 and hi - lo < min_gray:
        mid = (lo + hi) / 2.0
        lo = round(max(0.0, mid - min_gray / 2), 2)
        hi = round(min(1.0, mid + min_gray / 2), 2)
        import logging
        logging.getLogger(__name__).warning(
            "Zona gris insuficiente: umbrales ajustados a lo=%.2f hi=%.2f "
            "para que el LLM siga resolviendo (y enseñando) los casos dudosos.",
            lo, hi,
        )

    return lo, hi


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena el prefilter local")
    parser.add_argument(
        "--log", type=str, default=None,
        help="JSONL de decisiones (default: logs/filter_decisions.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Bundle joblib (default: data/models/prefilter.joblib)",
    )
    parser.add_argument("--min-samples", type=int, default=200)
    parser.add_argument("--keep-precision", type=float, default=0.98)
    parser.add_argument("--drop-precision", type=float, default=0.98)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    import joblib
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline

    from src.core.paths import LOGS_DIR
    from src.scraper.prefilter import DEFAULT_PREFILTER_PATH

    log_path = Path(args.log) if args.log else LOGS_DIR / "filter_decisions.jsonl"
    output_path = Path(args.output) if args.output else DEFAULT_PREFILTER_PATH

    if not log_path.exists():
        print(f"✗ No existe {log_path}.")
        print("  El log se llena corriendo el scraper con filter LLM activo.")
        print("  (Desde esta versión cada decisión guarda text_head — las")
        print("  corridas viejas sin text_head no sirven para entrenar.)")
        return

    texts, labels = load_decisions(log_path)
    n_political = sum(labels)
    print(f"Decisiones utilizables: {len(texts)} "
          f"({n_political} políticas, {len(texts) - n_political} no-políticas)")

    if len(texts) < args.min_samples or n_political == 0 or n_political == len(texts):
        print(f"✗ Insuficientes para entrenar (mínimo {args.min_samples} con ambas "
              "clases). Sigue acumulando decisiones del LLM y reintenta.")
        return

    x_train, x_val, y_train, y_val = train_test_split(
        texts, labels, test_size=0.25, random_state=args.seed, stratify=labels,
    )

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=50_000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            strip_accents="unicode",
            lowercase=True,
        )),
        ("clf", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            C=1.0,
            random_state=args.seed,
        )),
    ])
    pipeline.fit(x_train, y_train)

    val_probs = pipeline.predict_proba(x_val)[:, 1]
    auc = roc_auc_score(y_val, val_probs)
    lo, hi = calibrate_thresholds(
        val_probs, y_val, args.keep_precision, args.drop_precision,
    )

    resolved = sum(1 for p in val_probs if p <= lo or p >= hi)
    coverage = resolved / len(val_probs)

    meta = {
        "n_samples": len(texts),
        "n_political": n_political,
        "val_auc": round(float(auc), 4),
        "coverage_without_llm": round(coverage, 4),
        "keep_precision_target": args.keep_precision,
        "drop_precision_target": args.drop_precision,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "log_path": str(log_path),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: un Ctrl+C durante el dump dejaba un bundle corrupto
    # que crasheaba el scraper al arrancar con --prefilter.
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    joblib.dump({"pipeline": pipeline, "lo": lo, "hi": hi, "meta": meta}, tmp_path)
    tmp_path.replace(output_path)

    print()
    print("=" * 60)
    print("  PREFILTER ENTRENADO")
    print(f"  AUC (validación):     {auc:.4f}")
    print(f"  Umbrales:             lo={lo:.2f}  hi={hi:.2f}")
    print(f"  Resuelto sin LLM:     {coverage:.1%} del tráfico (en validación)")
    print(f"  Bundle:               {output_path}")
    print("=" * 60)
    print("\nÚsalo con: python scripts/scraper.py --prefilter")


if __name__ == "__main__":
    main()
