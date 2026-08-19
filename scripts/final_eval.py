"""Evaluación FINAL en test (P3.1) — se corre UNA vez, con el modelo ganador.

Protocolo del anteproyecto (OE3): el benchmark selecciona el mejor encoder
con métricas de VALIDACIÓN; este script evalúa ese único modelo contra el
test set (gold humano) y genera el reporte de evaluación:
- Precision / Recall / F1-Score Macro + Accuracy
- Métricas POR CLASE
- Matriz de confusión por categoría
- Análisis de errores: confusiones más frecuentes y errores entre PARES
  OPUESTOS (populismo↔institucionalismo, etc.), que son los más graves.

Uso:
    python scripts/final_eval.py --checkpoint logs/checkpoints/<alias>/best.ckpt
    python scripts/final_eval.py --checkpoint ... --report reports/evaluacion_final.md
"""

import argparse
import json
from pathlib import Path

import pytorch_lightning as L
from omegaconf import OmegaConf

from src.core.paths import CONFIGS_DIR, ROOT
from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES, OPPOSITE_PAIRS
from src.training.data.datamodule import IdeoGraphDataModule
from src.training.models.ideoclassifier import IdeoClassifier


def error_analysis(confmat: list[list[float]]) -> dict:
    """Confusiones más frecuentes y errores entre pares opuestos."""
    n = len(confmat)
    total_errors = sum(
        confmat[i][j] for i in range(n) for j in range(n) if i != j
    )

    confusions = sorted(
        (
            {
                "true": IDEOLOGY_CLASSES[i],
                "pred": IDEOLOGY_CLASSES[j],
                "count": int(confmat[i][j]),
            }
            for i in range(n) for j in range(n)
            if i != j and confmat[i][j] > 0
        ),
        key=lambda c: -c["count"],
    )

    opposite_errors = 0
    for a, b in OPPOSITE_PAIRS:
        i, j = CLASS_TO_IDX[a], CLASS_TO_IDX[b]
        opposite_errors += confmat[i][j] + confmat[j][i]

    return {
        "total_errors": int(total_errors),
        "opposite_pair_errors": int(opposite_errors),
        "opposite_pair_ratio": (
            round(opposite_errors / total_errors, 4) if total_errors else 0.0
        ),
        "top_confusions": confusions[:10],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluación final en test (P3.1)")
    parser.add_argument("--checkpoint", required=True, help="Checkpoint del modelo ganador")
    parser.add_argument(
        "--report", type=str, default=None,
        help="Reporte markdown (default: reports/evaluacion_final.md)",
    )
    args = parser.parse_args()

    ckpt_path = Path(args.checkpoint)
    if not ckpt_path.exists():
        print(f"✗ No existe {ckpt_path}")
        return

    report_path = Path(args.report) if args.report else ROOT / "reports" / "evaluacion_final.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Config de datos por defecto (mismo dataset/splits que el benchmark)
    data_cfg = OmegaConf.load(CONFIGS_DIR / "data" / "default.yaml")

    model = IdeoClassifier.load_from_checkpoint(str(ckpt_path))
    datamodule = IdeoGraphDataModule(
        data_path=data_cfg.data_path,
        model_name=model.hparams.model_name,
        batch_size=data_cfg.batch_size,
        num_workers=data_cfg.num_workers,
        pin_memory=data_cfg.pin_memory,
        seed=data_cfg.seed,
        splits_path=data_cfg.get("splits_path", None),
        chunk_size=data_cfg.chunk_size,
        chunk_stride=data_cfg.chunk_stride,
        max_chunks=data_cfg.max_chunks,
        chunking_strategy=data_cfg.chunking_strategy,
    )

    # Verificación de procedencia del test: el reporte de tesis exige gold humano
    splits_path = Path(data_cfg.get("splits_path", ""))
    test_label_source = "?"
    if splits_path.exists():
        with open(splits_path, encoding="utf-8") as f:
            test_label_source = json.load(f).get("test_label_source", "legacy")
    if test_label_source != "human":
        print("=" * 70)
        print("  ⚠ ADVERTENCIA: el test NO tiene etiquetas humanas "
              f"(test_label_source={test_label_source}).")
        print("  Este reporte NO es válido para el OE3 de la tesis.")
        print("=" * 70)

    trainer = L.Trainer(accelerator="auto", devices=1, logger=False)
    results = trainer.test(model, datamodule=datamodule)

    confmat = model.test_confmat_final.tolist()
    per_class = model.test_per_class_final
    analysis = error_analysis(confmat)
    metrics = results[0] if results else {}

    lines = [
        "# Evaluación final del clasificador (P3.1)",
        "",
        f"- Checkpoint: `{ckpt_path}`",
        f"- Encoder: `{model.hparams.model_name}`",
        f"- Test: {int(sum(sum(row) for row in confmat))} artículos "
        f"(etiquetas: **{test_label_source}**)",
        "",
        "## Métricas globales",
        "",
        "| Métrica | Valor |",
        "|---------|-------|",
        *[
            f"| {name.split('/')[-1]} | {value:.4f} |"
            for name, value in sorted(metrics.items())
        ],
        "",
        "## Métricas por clase",
        "",
        "| Clase | Precision | Recall | F1 | Soporte |",
        "|-------|-----------|--------|----|---------|",
        *[
            f"| {cls} | {m['precision']:.3f} | {m['recall']:.3f} "
            f"| {m['f1']:.3f} | {m['support']} |"
            for cls, m in per_class.items()
        ],
        "",
        "## Matriz de confusión (filas = real, columnas = predicha)",
        "",
        "| real \\ pred | " + " | ".join(IDEOLOGY_CLASSES) + " |",
        "|" + "|".join(["----"] * (len(IDEOLOGY_CLASSES) + 1)) + "|",
        *[
            f"| **{IDEOLOGY_CLASSES[i]}** | "
            + " | ".join(str(int(confmat[i][j])) for j in range(len(IDEOLOGY_CLASSES)))
            + " |"
            for i in range(len(IDEOLOGY_CLASSES))
        ],
        "",
        "## Análisis de errores",
        "",
        f"- Errores totales: {analysis['total_errors']}",
        f"- Errores entre PARES OPUESTOS: {analysis['opposite_pair_errors']} "
        f"({analysis['opposite_pair_ratio']:.1%} de los errores) — son los más "
        "graves: confundir una clase con su opuesta invierte la lectura ideológica.",
        "",
        "Confusiones más frecuentes:",
        "",
        "| Real | Predicha | n |",
        "|------|----------|---|",
        *[
            f"| {c['true']} | {c['pred']} | {c['count']} |"
            for c in analysis["top_confusions"]
        ],
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # JSON crudo junto al markdown (para figuras del documento de tesis)
    json_path = report_path.with_suffix(".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "checkpoint": str(ckpt_path),
                "test_label_source": test_label_source,
                "metrics": metrics,
                "per_class": per_class,
                "confusion_matrix": confmat,
                "error_analysis": analysis,
            },
            f, ensure_ascii=False, indent=2, default=str,
        )

    print(f"\n✓ Reporte: {report_path}")
    print(f"✓ JSON:    {json_path}")


if __name__ == "__main__":
    main()
