"""Genera reporte comparativo después de un benchmark.

Lee `logs/benchmark/<encoder_alias>/metrics.json` de cada modelo entrenado
y produce:
- Tabla comparativa MSE/R² por eje (Markdown)
- CSV con todas las métricas
- Gráficos (PNG) comparando los modelos:
    * Bar chart de R² por eje
    * Bar chart de MSE por eje
    * Radar chart con R² promedio por modelo

Uso:
    python scripts/compare_models.py
    python scripts/compare_models.py --output-dir reports/
"""

import argparse
import csv
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AXES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]


def load_all_metrics(benchmark_dir: Path) -> list[dict]:
    """Carga métricas de todos los modelos entrenados."""
    results: list[dict] = []
    if not benchmark_dir.exists():
        return results
    for subdir in sorted(benchmark_dir.iterdir()):
        if not subdir.is_dir():
            continue
        metrics_file = subdir / "metrics.json"
        if metrics_file.exists():
            with open(metrics_file, encoding="utf-8") as f:
                results.append(json.load(f))
    return results


def extract_axis_metric(test_metrics: dict, metric_type: str, axis: str) -> float | None:
    """Extrae una métrica específica (mse o r2) de un eje.

    Las métricas de Lightning vienen como 'val/mse_personalismo' o 'test/mse_personalismo'.
    Probamos ambos prefijos.
    """
    for prefix in ("test", "val"):
        key = f"{prefix}/{metric_type}_{axis}"
        if key in test_metrics:
            return test_metrics[key]
    return None


def build_markdown_report(metrics_list: list[dict]) -> str:
    """Construye el reporte completo en Markdown."""
    lines: list[str] = []
    lines.append("# Benchmark IdeoGraphCO — Reporte comparativo\n")

    if not metrics_list:
        lines.append("⚠️ No se encontraron métricas en `logs/benchmark/`.\n")
        lines.append("Corre primero `python scripts/benchmark.py`.\n")
        return "\n".join(lines)

    # Configuración común
    first = metrics_list[0]
    cfg = first.get("config", {})
    lines.append("## Configuración\n")
    lines.append(f"- **Dataset**: `{cfg.get('data', {}).get('data_path', '?')}`")
    trainer_cfg = cfg.get("trainer", {})
    lines.append(f"- **Epochs máximo**: {trainer_cfg.get('max_epochs', '?')}")
    lines.append(f"- **Batch size**: {cfg.get('data', {}).get('batch_size', '?')}")
    model_cfg = cfg.get("model", {})
    lines.append(f"- **Learning rate**: {model_cfg.get('learning_rate', '?')}")
    lines.append(f"- **Modelos comparados**: {len(metrics_list)}\n")

    # Tabla resumen global
    lines.append("## Resultados globales\n")
    lines.append("| Modelo | Best Val Loss | Avg R² | Avg MSE | Train time |")
    lines.append("|--------|---------------|--------|---------|------------|")

    for m in metrics_list:
        alias = m["encoder_alias"]
        val_loss = m.get("best_val_loss")
        test = m.get("test_metrics", {})

        r2_values = [extract_axis_metric(test, "r2", ax) for ax in AXES]
        r2_values = [v for v in r2_values if v is not None]
        avg_r2 = sum(r2_values) / len(r2_values) if r2_values else 0

        mse_values = [extract_axis_metric(test, "mse", ax) for ax in AXES]
        mse_values = [v for v in mse_values if v is not None]
        avg_mse = sum(mse_values) / len(mse_values) if mse_values else 0

        train_min = m.get("train_duration_seconds", 0) / 60

        val_loss_str = f"{val_loss:.4f}" if val_loss is not None else "N/A"
        lines.append(
            f"| **{alias}** | {val_loss_str} | {avg_r2:.3f} | {avg_mse:.4f} | {train_min:.1f} min |"
        )
    lines.append("")

    # Tabla R² por eje
    lines.append("## R² por eje (mayor = mejor)\n")
    header = "| Eje | " + " | ".join(m["encoder_alias"] for m in metrics_list) + " | Mejor |"
    sep = "|-----|" + "|".join(["----------"] * (len(metrics_list) + 1)) + "|"
    lines.append(header)
    lines.append(sep)

    for axis in AXES:
        row_values = []
        for m in metrics_list:
            v = extract_axis_metric(m.get("test_metrics", {}), "r2", axis)
            row_values.append(v if v is not None else float("-inf"))

        winner_idx = row_values.index(max(row_values))
        winner_alias = metrics_list[winner_idx]["encoder_alias"]

        cells = []
        for v in row_values:
            cells.append(f"{v:.3f}" if v != float("-inf") else "N/A")
        lines.append(f"| {axis.capitalize()} | {' | '.join(cells)} | **{winner_alias}** |")
    lines.append("")

    # Tabla MSE por eje
    lines.append("## MSE por eje (menor = mejor)\n")
    lines.append(header)
    lines.append(sep)

    for axis in AXES:
        row_values = []
        for m in metrics_list:
            v = extract_axis_metric(m.get("test_metrics", {}), "mse", axis)
            row_values.append(v if v is not None else float("inf"))

        winner_idx = row_values.index(min(row_values))
        winner_alias = metrics_list[winner_idx]["encoder_alias"]

        cells = []
        for v in row_values:
            cells.append(f"{v:.4f}" if v != float("inf") else "N/A")
        lines.append(f"| {axis.capitalize()} | {' | '.join(cells)} | **{winner_alias}** |")
    lines.append("")

    # Conclusiones automáticas
    lines.append("## Análisis\n")
    wins_r2: dict[str, int] = {m["encoder_alias"]: 0 for m in metrics_list}
    for axis in AXES:
        scores = [
            (m["encoder_alias"], extract_axis_metric(m.get("test_metrics", {}), "r2", axis) or -1)
            for m in metrics_list
        ]
        winner = max(scores, key=lambda x: x[1])
        wins_r2[winner[0]] += 1

    lines.append("**Victorias por R² (cuántos ejes gana cada modelo):**\n")
    for alias, count in sorted(wins_r2.items(), key=lambda x: -x[1]):
        lines.append(f"- **{alias}**: {count}/{len(AXES)} ejes")
    lines.append("")

    return "\n".join(lines)


def write_csv(metrics_list: list[dict], output_path: Path) -> None:
    """Escribe todas las métricas en formato CSV (una fila por modelo×eje)."""
    rows: list[dict] = []
    for m in metrics_list:
        alias = m["encoder_alias"]
        train_min = m.get("train_duration_seconds", 0) / 60
        test = m.get("test_metrics", {})
        for axis in AXES:
            rows.append({
                "encoder": alias,
                "model_name": m["model_name"],
                "axis": axis,
                "test_r2": extract_axis_metric(test, "r2", axis),
                "test_mse": extract_axis_metric(test, "mse", axis),
                "train_minutes": round(train_min, 2),
                "best_val_loss": m.get("best_val_loss"),
            })

    if not rows:
        return

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_charts(metrics_list: list[dict], output_dir: Path) -> None:
    """Genera gráficos comparativos (PNG) usando matplotlib si está disponible."""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        logger.warning("matplotlib no instalado, saltando gráficos. pip install matplotlib")
        return

    aliases = [m["encoder_alias"] for m in metrics_list]
    n_axes = len(AXES)
    x = np.arange(n_axes)
    width = 0.8 / len(aliases)

    # --- R² por eje ---
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, m in enumerate(metrics_list):
        values = [
            extract_axis_metric(m.get("test_metrics", {}), "r2", a) or 0
            for a in AXES
        ]
        ax.bar(x + i * width - 0.4 + width / 2, values, width, label=aliases[i])
    ax.set_xticks(x)
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES], rotation=20)
    ax.set_ylabel("R²")
    ax.set_title("R² por eje y modelo (mayor es mejor)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "r2_per_axis.png", dpi=120)
    plt.close(fig)

    # --- MSE por eje ---
    fig, ax = plt.subplots(figsize=(14, 6))
    for i, m in enumerate(metrics_list):
        values = [
            extract_axis_metric(m.get("test_metrics", {}), "mse", a) or 0
            for a in AXES
        ]
        ax.bar(x + i * width - 0.4 + width / 2, values, width, label=aliases[i])
    ax.set_xticks(x)
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES], rotation=20)
    ax.set_ylabel("MSE")
    ax.set_title("MSE por eje y modelo (menor es mejor)")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_dir / "mse_per_axis.png", dpi=120)
    plt.close(fig)

    # --- Radar chart de R² promedio ---
    angles = np.linspace(0, 2 * np.pi, n_axes, endpoint=False).tolist()
    angles += angles[:1]  # cerrar polígono

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    for m in metrics_list:
        values = [
            extract_axis_metric(m.get("test_metrics", {}), "r2", a) or 0
            for a in AXES
        ]
        values += values[:1]
        ax.plot(angles, values, label=m["encoder_alias"], linewidth=2)
        ax.fill(angles, values, alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([a.capitalize()[:10] for a in AXES])
    ax.set_ylim(0, 1)
    ax.set_title("Comparación de R² por eje")
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
    metrics_list = load_all_metrics(benchmark_dir)
    logger.info("Encontrados %d modelos entrenados", len(metrics_list))

    if not metrics_list:
        logger.error("No hay métricas. Corre primero `python scripts/benchmark.py`.")
        return

    # Reporte Markdown
    report = build_markdown_report(metrics_list)
    report_path = output_dir / "benchmark_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info("✓ Reporte Markdown: %s", report_path)

    # CSV con todas las métricas
    csv_path = output_dir / "benchmark_metrics.csv"
    write_csv(metrics_list, csv_path)
    logger.info("✓ CSV: %s", csv_path)

    # Gráficos
    write_charts(metrics_list, output_dir)
    logger.info("✓ Gráficos: %s/r2_per_axis.png, mse_per_axis.png, radar_comparison.png", output_dir)

    print(f"\n✓ Reporte completo en: {output_dir}")


if __name__ == "__main__":
    main()
