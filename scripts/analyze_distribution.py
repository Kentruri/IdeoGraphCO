"""Analiza la distribución de scores por eje en el dataset etiquetado.

Útil para identificar ejes con poca varianza (donde el modelo no podrá aprender
mucho) ANTES de gastar horas en un benchmark.

Uso:
    python scripts/analyze_distribution.py
    python scripts/analyze_distribution.py --input data/interim/labeled_news_clean.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AXES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza distribución de scores por eje")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL etiquetado (default: data/interim/labeled_news_clean.jsonl)",
    )
    parser.add_argument(
        "--thresholds", nargs="+", type=float, default=[0.3, 0.5, 0.7],
        help="Umbrales para contar artículos por encima (default: 0.3 0.5 0.7)",
    )
    args = parser.parse_args()

    from src.paths import INTERIM_DIR

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news_clean.jsonl"
    if not input_path.exists():
        fallback = INTERIM_DIR / "labeled_news.jsonl"
        if fallback.exists():
            logger.warning("No existe %s, usando %s", input_path, fallback)
            input_path = fallback
        else:
            logger.error("No existe ningún JSONL etiquetado.")
            return

    # Recolectar scores por eje
    scores: dict[str, list[float]] = {a: [] for a in AXES}
    n_political = 0
    n_total = 0
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sample = json.loads(line)
            n_total += 1
            if sample.get("is_political") != 1:
                continue
            n_political += 1
            nested = sample.get("labels", {})
            for axis in AXES:
                v = float(sample.get(axis, nested.get(axis, 0.0)))
                scores[axis].append(v)

    print()
    print("=" * 70)
    print("  DISTRIBUCIÓN DE SCORES POR EJE")
    print(f"  Fuente: {input_path}")
    print(f"  Total artículos: {n_total} (políticos: {n_political})")
    print("=" * 70)
    print()

    # Tabla
    header_thresh = "  ".join(f">={t:.1f}" for t in args.thresholds)
    print(f"{'Eje':<20} {'Media':>7} {'Std':>7} {'Var':>7}  {header_thresh}  Warning")
    print("-" * 70)

    for axis in AXES:
        vals = scores[axis]
        if not vals:
            print(f"{axis:<20} (sin datos)")
            continue
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        std = var ** 0.5

        # Contar artículos sobre cada umbral
        counts = [sum(1 for v in vals if v >= t) for t in args.thresholds]
        count_str = "  ".join(f"{c:>4}" for c in counts)

        # Warnings sobre datos escasos
        warning = ""
        if counts[-1] < 30:
            warning = "⚠️ <30 muestras altas"
        if var < 0.01:
            warning = "⚠️ varianza muy baja"

        print(f"{axis:<20} {mean:>7.3f} {std:>7.3f} {var:>7.3f}  {count_str}  {warning}")

    print()
    print("Interpretación:")
    print("  - Ejes con var < 0.01: el modelo apenas puede aprender (sin varianza)")
    print("  - Ejes con < 30 muestras altas: el modelo va a sobreajustar a esos pocos")
    print("  - Antes del benchmark: considerar más datos para los ejes débiles")
    print()


if __name__ == "__main__":
    main()
