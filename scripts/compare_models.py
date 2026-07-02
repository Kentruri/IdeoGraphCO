"""Reporte comparativo del benchmark del clasificador multiclase.

Lee `logs/benchmark/<alias>__seed<N>/metrics.json` y produce:
- Tabla comparativa de F1 Macro / Precision / Recall / Accuracy (Markdown)
- CSV con todas las métricas
- Gráficos:
    * Bar chart de F1 Macro por modelo (con errorbars si hay multi-seed)
    * Matriz de confusión de cada modelo (media entre semillas si hay varias)

Agrupa automáticamente por encoder cuando hay múltiples semillas: reporta
media ± std.

Uso:
    python scripts/compare_models.py
    python scripts/compare_models.py --output-dir reports/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
from collections import defaultdict
from pathlib import Path

from src.core.schema import IDEOLOGY_CLASSES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Métricas principales que reporta test_metrics del checkpoint (según
# IdeoClassifier._eval_epoch_end).
CLASSIFICATION_METRICS: list[str] = [
    "f1_macro", "precision_macro", "recall_macro", "accuracy",
]

_RUN_KEY_RE = re.compile(r"^(?P<encoder>.+?)__seed(?P<seed>\d+)$")


def load_all_metrics(benchmark_dir: Path) -> list[dict]:
    """Carga métricas de todos los runs (cada uno = encoder × seed)."""
    results: list[dict] = []
    if not benchmark_dir.exists():
        return results
    for subdir in sorted(benchmark_dir.iterdir()):
        if not subdir.is_dir():
            continue
        metrics_file = subdir / "metrics.json"
        if not metrics_file.exists():
            continue
        with open(metrics_file, encoding="utf-8") as f:
            data = json.load(f)

        match = _RUN_KEY_RE.match(subdir.name)
        if match:
            data["_encoder_canonical"] = match.group("encoder")
            data["_seed"] = int(match.group("seed"))
        else:
            data["_encoder_canonical"] = data.get("encoder_alias", subdir.name)
            data["_seed"] = data.get("seed", 0)
        results.append(data)
    return results


def extract_metric(test_metrics: dict, metric_name: str) -> float | None:
    """Extrae una métrica del bloque test_metrics (prefiere test/ sobre val/)."""
    for prefix in ("test", "val"):
        key = f"{prefix}/{metric_name}"
        if key in test_metrics:
            return float(test_metrics[key])
    return None


def _mean_std(values: list[float]) -> dict[str, float]:
    values = [v for v in values if v is not None and v == v]  # sin NaN/None
    if not values:
        return {"mean": float("nan"), "std": 0.0}
    n = len(values)
    mean = sum(values) / n
    if n == 1:
        return {"mean": mean, "std": 0.0}
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return {"mean": mean, "std": var ** 0.5}


def aggregate_by_encoder(runs: list[dict]) -> dict[str, dict]:
    """Agrupa runs por encoder canónico y calcula media/std por métrica."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        grouped[r["_encoder_canonical"]].append(r)

    out: dict[str, dict] = {}
    for encoder, encoder_runs in grouped.items():
        seeds = sorted(r["_seed"] for r in encoder_runs)
        train_mins = [r.get("train_duration_seconds", 0) / 60 for r in encoder_runs]
        val_losses = [
            r["best_val_loss"] for r in encoder_runs
            if r.get("best_val_loss") is not None
        ]

        metrics_stats: dict[str, dict] = {}
        for metric in CLASSIFICATION_METRICS:
            vals = [
                extract_metric(r.get("test_metrics", {}), metric)
                for r in encoder_runs
            ]
            metrics_stats[metric] = _mean_std(vals)

        # Matriz de confusión promedio entre semillas (misma dimensión NxN)
        confmats = [
            r.get("test_confusion_matrix") for r in encoder_runs
            if r.get("test_confusion_matrix")
        ]
        confmat_avg: list[list[float]] | None = None
        if confmats:
            n = len(confmats[0])
            confmat_avg = [
                [
                    sum(cm[i][j] for cm in confmats) / len(confmats)
                    for j in range(n)
                ]
                for i in range(n)
            ]

        out[encoder] = {
            "n_seeds": len(encoder_runs),
            "seeds": seeds,
            "train_minutes": _mean_std(train_mins),
            "best_val_loss": _mean_std(val_losses),
            "metrics": metrics_stats,
            "confusion_matrix": confmat_avg,
            "model_name": encoder_runs[0].get("model_name", ""),
            "git_commit": encoder_runs[0].get("git_commit"),
        }
    return out


def _fmt(mean: float, std: float, decimals: int = 3, show_std: bool = True) -> str:
    if not show_std or std == 0:
        return f"{mean:.{decimals}f}"
    return f"{mean:.{decimals}f} ± {std:.{decimals}f}"


def build_markdown_report(
    aggregated: dict[str, dict],
    runs: list[dict],
) -> str:
    lines: list[str] = ["# Benchmark IdeoGraphCO — Reporte comparativo\n"]

    if not aggregated:
        lines.append("⚠️ No se encontraron métricas. Corre `python scripts/benchmark.py`.\n")
        return "\n".join(lines)

    first_run = runs[0]
    cfg = first_run.get("config", {})
    lines.append("## Configuración\n")
    lines.append(f"- **Dataset**: `{cfg.get('data', {}).get('data_path', '?')}`")
    lines.append(f"- **Epochs**: {cfg.get('trainer', {}).get('max_epochs', '?')}")
    lines.append(f"- **Batch size**: {cfg.get('data', {}).get('batch_size', '?')}")
    lines.append(f"- **Learning rate**: {cfg.get('model', {}).get('learning_rate', '?')}")
    lines.append(f"- **Chunk size**: {cfg.get('data', {}).get('chunk_size', '?')}")
    lines.append(f"- **Max chunks**: {cfg.get('data', {}).get('max_chunks', '?')}")
    lines.append(f"- **Precision**: {first_run.get('precision_used', '?')}")
    lines.append(f"- **Git commit**: `{first_run.get('git_commit', 'N/A')}`\n")

    encoders = sorted(aggregated.keys())
    n_seeds = aggregated[encoders[0]]["n_seeds"]
    show_std = n_seeds > 1
    lines.append(f"- **Semillas**: {n_seeds}")
    if show_std:
        lines.append("  - Reporta media ± std")
    lines.append("")

    # Tabla resumen
    lines.append("## Resultados globales\n")
    lines.append("| Modelo | F1 Macro | Precision Macro | Recall Macro | Accuracy | Best val loss | Train (min) |")
    lines.append("|--------|----------|-----------------|--------------|----------|---------------|-------------|")
    for enc in encoders:
        agg = aggregated[enc]
        m = agg["metrics"]
        row = [
            f"**{enc}**",
            _fmt(m["f1_macro"]["mean"], m["f1_macro"]["std"], 3, show_std),
            _fmt(m["precision_macro"]["mean"], m["precision_macro"]["std"], 3, show_std),
            _fmt(m["recall_macro"]["mean"], m["recall_macro"]["std"], 3, show_std),
            _fmt(m["accuracy"]["mean"], m["accuracy"]["std"], 3, show_std),
            _fmt(agg["best_val_loss"]["mean"], agg["best_val_loss"]["std"], 4, show_std),
            _fmt(agg["train_minutes"]["mean"], agg["train_minutes"]["std"], 1, show_std),
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    # Análisis: ganador global
    lines.append("## Ganador por métrica principal\n")
    for metric in CLASSIFICATION_METRICS:
        ranking = sorted(
            [(enc, aggregated[enc]["metrics"][metric]["mean"]) for enc in encoders],
            key=lambda x: -x[1] if x[1] == x[1] else float("inf"),
        )
        best_enc, best_val = ranking[0]
        lines.append(f"- **{metric}** → `{best_enc}` ({best_val:.3f})")
    lines.append("")

    # Confusion matrix por modelo (Markdown, valores redondeados)
    lines.append("## Matriz de confusión (test set)\n")
    for enc in encoders:
        cm = aggregated[enc]["confusion_matrix"]
        if cm is None:
            continue
        lines.append(f"### {enc}\n")
        header = "| pred → | " + " | ".join(IDEOLOGY_CLASSES) + " |"
        sep = "|--------|" + "|".join(["----"] * len(IDEOLOGY_CLASSES)) + "|"
        lines.append(header)
        lines.append(sep)
        for i, true_cls in enumerate(IDEOLOGY_CLASSES):
            row_vals = [f"{cm[i][j]:.1f}" for j in range(len(IDEOLOGY_CLASSES))]
            lines.append(f"| **{true_cls}** | " + " | ".join(row_vals) + " |")
        lines.append("")

    if not show_std:
        lines.append(
            "> ⚠️ Resultados de **una sola semilla**. Para conclusiones "
            "estadísticamente sólidas correr `--seeds 42 43 44`.\n"
        )

    return "\n".join(lines)


def write_csv(runs: list[dict], output_path: Path) -> None:
    """Fila por encoder × seed × métrica."""
    rows: list[dict] = []
    for r in runs:
        encoder = r["_encoder_canonical"]
        seed = r["_seed"]
        train_min = r.get("train_duration_seconds", 0) / 60
        test = r.get("test_metrics", {})
        for metric in CLASSIFICATION_METRICS:
            rows.append({
                "encoder": encoder,
                "seed": seed,
                "model_name": r.get("model_name", ""),
                "metric": metric,
                "value": extract_metric(test, metric),
                "train_minutes": round(train_min, 2),
                "best_val_loss": r.get("best_val_loss"),
                "git_commit": r.get("git_commit"),
            })
    if not rows:
        return
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_charts(aggregated: dict[str, dict], output_dir: Path) -> None:
    """Gráficos: F1 Macro por modelo, matriz de confusión."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib no instalado, saltando gráficos.")
        return

    encoders = sorted(aggregated.keys())
    n_seeds = aggregated[encoders[0]]["n_seeds"]
    show_errorbars = n_seeds > 1

    # --- F1 macro por modelo ---
    fig, ax = plt.subplots(figsize=(9, 5))
    values = [aggregated[e]["metrics"]["f1_macro"]["mean"] for e in encoders]
    errors = [aggregated[e]["metrics"]["f1_macro"]["std"] for e in encoders] if show_errorbars else None
    ax.bar(encoders, values, yerr=errors, capsize=4)
    ax.set_ylabel("F1 Macro")
    title = "F1 Macro por encoder"
    if show_errorbars:
        title += f" — media ± std sobre {n_seeds} semillas"
    ax.set_title(title)
    ax.set_ylim(0, 1)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "f1_macro_per_encoder.png", dpi=120)
    plt.close(fig)

    # --- Matriz de confusión por encoder ---
    for enc in encoders:
        cm = aggregated[enc]["confusion_matrix"]
        if cm is None:
            continue
        cm_arr = np.array(cm)
        fig, ax = plt.subplots(figsize=(8, 7))
        im = ax.imshow(cm_arr, cmap="Blues", aspect="auto")
        fig.colorbar(im, ax=ax)
        ax.set_xticks(range(len(IDEOLOGY_CLASSES)))
        ax.set_yticks(range(len(IDEOLOGY_CLASSES)))
        ax.set_xticklabels(IDEOLOGY_CLASSES, rotation=45, ha="right")
        ax.set_yticklabels(IDEOLOGY_CLASSES)
        ax.set_xlabel("Predicción")
        ax.set_ylabel("Real")
        ax.set_title(f"Matriz de confusión — {enc}")
        for i in range(len(IDEOLOGY_CLASSES)):
            for j in range(len(IDEOLOGY_CLASSES)):
                ax.text(
                    j, i, f"{cm_arr[i, j]:.0f}", ha="center", va="center",
                    color="white" if cm_arr[i, j] > cm_arr.max() / 2 else "black",
                    fontsize=9,
                )
        fig.tight_layout()
        fig.savefig(output_dir / f"confusion_matrix_{enc}.png", dpi=120)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte comparativo del benchmark")
    parser.add_argument("--benchmark-dir", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    from src.core.paths import LOGS_DIR, ROOT

    benchmark_dir = Path(args.benchmark_dir) if args.benchmark_dir else LOGS_DIR / "benchmark"
    output_dir = Path(args.output_dir) if args.output_dir else ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Cargando métricas desde %s", benchmark_dir)
    runs = load_all_metrics(benchmark_dir)
    logger.info("Encontradas %d corridas", len(runs))
    if not runs:
        logger.error("No hay métricas. Corre primero `python scripts/benchmark.py`.")
        return

    aggregated = aggregate_by_encoder(runs)
    logger.info("Modelos únicos: %d", len(aggregated))
    for enc, agg in aggregated.items():
        logger.info("  %s: %d semillas (%s)", enc, agg["n_seeds"], agg["seeds"])

    report = build_markdown_report(aggregated, runs)
    report_path = output_dir / "benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("[OK] Reporte Markdown: %s", report_path)

    csv_path = output_dir / "benchmark_metrics.csv"
    write_csv(runs, csv_path)
    logger.info("[OK] CSV: %s", csv_path)

    write_charts(aggregated, output_dir)
    logger.info("[OK] Gráficos: %s", output_dir)

    print(f"\n[OK] Reporte completo en: {output_dir}")


if __name__ == "__main__":
    main()
