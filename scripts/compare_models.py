"""Genera reporte comparativo después de un benchmark.

Lee `logs/benchmark/<encoder_alias>__seed<N>/metrics.json` de cada corrida y produce:
- Tabla comparativa MSE/R² por eje (Markdown)
- CSV con todas las métricas (incluyendo todas las semillas)
- Gráficos (PNG) comparando los modelos:
    * Bar chart de R² por eje (con errorbars si hay multi-seed)
    * Bar chart de MSE por eje
    * Radar chart con R² promedio por modelo

Agrupa automáticamente por encoder cuando hay múltiples semillas: reporta
media ± std en lugar de un valor único.

Uso:
    python scripts/compare_models.py
    python scripts/compare_models.py --output-dir reports/
"""

import argparse
import csv
import json
import logging
import re
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AXES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]

# Regex para extraer encoder y seed del nombre del directorio
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

        # Determinar encoder canónico y seed desde el nombre del run dir
        match = _RUN_KEY_RE.match(subdir.name)
        if match:
            data["_encoder_canonical"] = match.group("encoder")
            data["_seed"] = int(match.group("seed"))
        else:
            data["_encoder_canonical"] = data.get("encoder_alias", subdir.name)
            data["_seed"] = data.get("seed", 0)
        results.append(data)
    return results


def extract_axis_metric(test_metrics: dict, metric_type: str, axis: str) -> float | None:
    """Extrae una métrica específica (mse o r2) de un eje.

    Prefiere test/ sobre val/ — si el modelo no tiene test_step se cae a val/.
    """
    for prefix in ("test", "val"):
        key = f"{prefix}/{metric_type}_{axis}"
        if key in test_metrics:
            return float(test_metrics[key])
    return None


def aggregate_by_encoder(runs: list[dict]) -> dict[str, dict]:
    """Agrupa runs por encoder canónico y calcula media/std de cada métrica.

    Returns:
        dict {encoder: {
            "n_seeds": int,
            "seeds": [42, 43, ...],
            "train_minutes": {"mean": ..., "std": ...},
            "best_val_loss": {"mean": ..., "std": ...},
            "axis": {axis: {"r2_mean": ..., "r2_std": ..., "mse_mean": ..., "mse_std": ...}}
        }}
    """
    from collections import defaultdict
    grouped: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        grouped[r["_encoder_canonical"]].append(r)

    def _mean_std(values: list[float]) -> dict[str, float]:
        if not values:
            return {"mean": float("nan"), "std": 0.0}
        n = len(values)
        mean = sum(values) / n
        if n == 1:
            return {"mean": mean, "std": 0.0}
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        return {"mean": mean, "std": var ** 0.5}

    out: dict[str, dict] = {}
    for encoder, encoder_runs in grouped.items():
        seeds = sorted(r["_seed"] for r in encoder_runs)
        train_mins = [r.get("train_duration_seconds", 0) / 60 for r in encoder_runs]
        val_losses = [
            r["best_val_loss"] for r in encoder_runs
            if r.get("best_val_loss") is not None
        ]

        axis_stats: dict[str, dict] = {}
        for axis in AXES:
            r2_vals = [
                extract_axis_metric(r.get("test_metrics", {}), "r2", axis)
                for r in encoder_runs
            ]
            r2_vals = [v for v in r2_vals if v is not None]
            mse_vals = [
                extract_axis_metric(r.get("test_metrics", {}), "mse", axis)
                for r in encoder_runs
            ]
            mse_vals = [v for v in mse_vals if v is not None]
            r2 = _mean_std(r2_vals)
            mse = _mean_std(mse_vals)
            axis_stats[axis] = {
                "r2_mean": r2["mean"],
                "r2_std": r2["std"],
                "mse_mean": mse["mean"],
                "mse_std": mse["std"],
            }

        out[encoder] = {
            "n_seeds": len(encoder_runs),
            "seeds": seeds,
            "train_minutes": _mean_std(train_mins),
            "best_val_loss": _mean_std(val_losses),
            "axis": axis_stats,
            "model_name": encoder_runs[0].get("model_name", ""),
            "git_commit": encoder_runs[0].get("git_commit"),
        }
    return out


def _format_mean_std(mean: float, std: float, decimals: int = 3, show_std: bool = True) -> str:
    """Formato: '0.452 ± 0.012' o '0.452' si std=0."""
    if not show_std or std == 0:
        return f"{mean:.{decimals}f}"
    return f"{mean:.{decimals}f} ± {std:.{decimals}f}"


def build_markdown_report(
    aggregated: dict[str, dict],
    runs: list[dict],
) -> str:
    """Construye el reporte completo en Markdown."""
    lines: list[str] = []
    lines.append("# Benchmark IdeoGraphCO — Reporte comparativo\n")

    if not aggregated:
        lines.append("⚠️ No se encontraron métricas en `logs/benchmark/`.\n")
        lines.append("Corre primero `python scripts/benchmark.py`.\n")
        return "\n".join(lines)

    # Configuración común
    first_run = runs[0]
    cfg = first_run.get("config", {})
    lines.append("## Configuración\n")
    lines.append(f"- **Dataset**: `{cfg.get('data', {}).get('data_path', '?')}`")
    trainer_cfg = cfg.get("trainer", {})
    lines.append(f"- **Epochs máximo**: {trainer_cfg.get('max_epochs', '?')}")
    lines.append(f"- **Batch size**: {cfg.get('data', {}).get('batch_size', '?')}")
    model_cfg = cfg.get("model", {})
    lines.append(f"- **Learning rate**: {model_cfg.get('learning_rate', '?')}")
    lines.append(f"- **Precision**: {first_run.get('precision_used', '?')}")
    lines.append(f"- **Git commit**: `{first_run.get('git_commit', 'N/A')}`\n")

    encoders = sorted(aggregated.keys())
    n_seeds = aggregated[encoders[0]]["n_seeds"]
    show_std = n_seeds > 1
    lines.append(f"- **Semillas usadas**: {n_seeds}")
    if show_std:
        lines.append(f"  - Reporta media ± std")
    lines.append("")

    # Tabla resumen global
    lines.append("## Resultados globales\n")
    lines.append("| Modelo | Best Val Loss | Avg R² | Avg MSE | Train time (min) |")
    lines.append("|--------|---------------|--------|---------|------------------|")

    for enc in encoders:
        agg = aggregated[enc]
        # Avg R² y MSE: promedio entre ejes (de las medias por eje)
        r2_means = [agg["axis"][a]["r2_mean"] for a in AXES]
        r2_means_valid = [v for v in r2_means if v == v]  # filtrar NaN
        avg_r2 = sum(r2_means_valid) / len(r2_means_valid) if r2_means_valid else float("nan")
        mse_means = [agg["axis"][a]["mse_mean"] for a in AXES]
        mse_means_valid = [v for v in mse_means if v == v]
        avg_mse = sum(mse_means_valid) / len(mse_means_valid) if mse_means_valid else float("nan")

        val_loss = _format_mean_std(
            agg["best_val_loss"]["mean"], agg["best_val_loss"]["std"], 4, show_std,
        )
        train_min = _format_mean_std(
            agg["train_minutes"]["mean"], agg["train_minutes"]["std"], 1, show_std,
        )
        lines.append(
            f"| **{enc}** | {val_loss} | {avg_r2:.3f} | {avg_mse:.4f} | {train_min} |"
        )
    lines.append("")

    # Tabla R² por eje (con std si hay multi-seed)
    lines.append("## R² por eje (mayor = mejor)\n")
    header = "| Eje | " + " | ".join(encoders) + " | Mejor |"
    sep = "|-----|" + "|".join(["----------"] * (len(encoders) + 1)) + "|"
    lines.append(header)
    lines.append(sep)

    for axis in AXES:
        cells = []
        means = []
        for enc in encoders:
            stat = aggregated[enc]["axis"][axis]
            means.append(stat["r2_mean"])
            cells.append(_format_mean_std(stat["r2_mean"], stat["r2_std"], 3, show_std))

        # Ganador: el de mayor media (manejar ties tomando el primero)
        winner_idx = means.index(max(means))
        winner = encoders[winner_idx]
        lines.append(f"| {axis.capitalize()} | {' | '.join(cells)} | **{winner}** |")
    lines.append("")

    # Tabla MSE por eje
    lines.append("## MSE por eje (menor = mejor)\n")
    lines.append(header)
    lines.append(sep)

    for axis in AXES:
        cells = []
        means = []
        for enc in encoders:
            stat = aggregated[enc]["axis"][axis]
            means.append(stat["mse_mean"])
            cells.append(_format_mean_std(stat["mse_mean"], stat["mse_std"], 4, show_std))

        winner_idx = means.index(min(means))
        winner = encoders[winner_idx]
        lines.append(f"| {axis.capitalize()} | {' | '.join(cells)} | **{winner}** |")
    lines.append("")

    # Análisis: victorias + rank promedio
    lines.append("## Análisis\n")

    wins_r2: dict[str, int] = {enc: 0 for enc in encoders}
    ranks_r2: dict[str, list[int]] = {enc: [] for enc in encoders}

    for axis in AXES:
        # Lista (encoder, r2_mean) ordenada de mayor a menor
        scores = sorted(
            [(enc, aggregated[enc]["axis"][axis]["r2_mean"]) for enc in encoders],
            key=lambda x: -x[1] if x[1] == x[1] else float("inf"),  # NaN al final
        )
        for rank, (enc, _) in enumerate(scores, 1):
            ranks_r2[enc].append(rank)
        wins_r2[scores[0][0]] += 1

    lines.append(f"### Victorias por R² (ejes ganados sobre {len(AXES)})\n")
    for enc, count in sorted(wins_r2.items(), key=lambda x: -x[1]):
        lines.append(f"- **{enc}**: {count}/{len(AXES)} ejes")
    lines.append("")

    lines.append("### Rank promedio (1 = mejor en cada eje, menor es mejor)\n")
    lines.append("| Modelo | Rank promedio | Ranks por eje |")
    lines.append("|--------|---------------|----------------|")
    for enc, ranks in sorted(ranks_r2.items(), key=lambda x: sum(x[1]) / len(x[1])):
        avg_rank = sum(ranks) / len(ranks)
        lines.append(f"| {enc} | {avg_rank:.2f} | {ranks} |")
    lines.append("")

    if not show_std:
        lines.append("> ⚠️ Resultados de **una sola semilla**. Para conclusiones "
                     "estadísticamente sólidas correr `--seeds 42 43 44`.\n")

    return "\n".join(lines)


def write_csv(runs: list[dict], output_path: Path) -> None:
    """Escribe todas las métricas (una fila por encoder × seed × eje)."""
    rows: list[dict] = []
    for r in runs:
        encoder = r["_encoder_canonical"]
        seed = r["_seed"]
        train_min = r.get("train_duration_seconds", 0) / 60
        test = r.get("test_metrics", {})
        for axis in AXES:
            rows.append({
                "encoder": encoder,
                "seed": seed,
                "model_name": r.get("model_name", ""),
                "axis": axis,
                "test_r2": extract_axis_metric(test, "r2", axis),
                "test_mse": extract_axis_metric(test, "mse", axis),
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
    """Genera gráficos comparativos (PNG) usando matplotlib si está disponible."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib no instalado, saltando gráficos. pip install matplotlib")
        return

    encoders = sorted(aggregated.keys())
    n_seeds = aggregated[encoders[0]]["n_seeds"]
    show_errorbars = n_seeds > 1

    n_axes = len(AXES)
    x = np.arange(n_axes)
    width = 0.8 / len(encoders)

    # --- R² por eje ---
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, enc in enumerate(encoders):
        values = [aggregated[enc]["axis"][a]["r2_mean"] for a in AXES]
        errors = [aggregated[enc]["axis"][a]["r2_std"] for a in AXES] if show_errorbars else None
        ax.bar(
            x + i * width - 0.4 + width / 2, values, width,
            yerr=errors, capsize=3, label=enc,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES], rotation=20)
    ax.set_ylabel("R²")
    title = "R² por eje y modelo (mayor es mejor)"
    if show_errorbars:
        title += f" — media ± std sobre {n_seeds} semillas"
    ax.set_title(title)
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    ax.axhline(0, color="black", linewidth=0.5, alpha=0.5)
    fig.tight_layout()
    fig.savefig(output_dir / "r2_per_axis.png", dpi=120)
    plt.close(fig)

    # --- MSE por eje ---
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, enc in enumerate(encoders):
        values = [aggregated[enc]["axis"][a]["mse_mean"] for a in AXES]
        errors = [aggregated[enc]["axis"][a]["mse_std"] for a in AXES] if show_errorbars else None
        ax.bar(
            x + i * width - 0.4 + width / 2, values, width,
            yerr=errors, capsize=3, label=enc,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES], rotation=20)
    ax.set_ylabel("MSE")
    ax.set_title("MSE por eje y modelo (menor es mejor)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "mse_per_axis.png", dpi=120)
    plt.close(fig)

    # --- Radar chart de R² (con ylim adaptativo) ---
    angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})

    # Calcular min global de R² para ylim adaptativo
    all_r2 = []
    for enc in encoders:
        for axis in AXES:
            v = aggregated[enc]["axis"][axis]["r2_mean"]
            if v == v:  # no NaN
                all_r2.append(v)
    y_min = min(min(all_r2, default=0), 0)  # incluir 0 para referencia
    y_max = max(max(all_r2, default=1), 1)
    # Pequeño padding visual
    y_padding = 0.1 * (y_max - y_min)
    y_min -= y_padding
    y_max += y_padding

    for enc in encoders:
        values = [aggregated[enc]["axis"][a]["r2_mean"] for a in AXES]
        values += values[:1]
        ax.plot(angles, values, label=enc, linewidth=2)
        ax.fill(angles, values, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES])
    ax.set_ylim(y_min, y_max)
    title = "R² por eje (radar)"
    if show_errorbars:
        title += f" — media sobre {n_seeds} semillas"
    ax.set_title(title)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
    fig.tight_layout()
    fig.savefig(output_dir / "radar_comparison.png", dpi=120)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reporte comparativo del benchmark")
    parser.add_argument(
        "--benchmark-dir", type=str, default=None,
        help="Directorio de benchmarks (default: logs/benchmark/)",
    )
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directorio de salida del reporte (default: reports/)",
    )
    args = parser.parse_args()

    from src.paths import LOGS_DIR, ROOT

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

    # Reporte Markdown
    report = build_markdown_report(aggregated, runs)
    report_path = output_dir / "benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("✓ Reporte Markdown: %s", report_path)

    # CSV con todas las métricas
    csv_path = output_dir / "benchmark_metrics.csv"
    write_csv(runs, csv_path)
    logger.info("✓ CSV: %s", csv_path)

    # Gráficos
    write_charts(aggregated, output_dir)
    logger.info("✓ Gráficos: %s/r2_per_axis.png, mse_per_axis.png, radar_comparison.png", output_dir)

    print(f"\n✓ Reporte completo en: {output_dir}")


if __name__ == "__main__":
    main()
