"""Script principal de entrenamiento — Hydra + Lightning + IdeoClassifier.

Usa el `model_name` definido en `configs/model/*.yaml` tanto para el encoder
como para el tokenizer (consistencia entre modelo y datos).

Al terminar, guarda métricas finales en
`logs/benchmark/<encoder_alias>/metrics.json` para que compare_models las
recolecte.
"""

import json
import shutil
import subprocess
import time
from pathlib import Path

import hydra
import pytorch_lightning as L
import torch
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from omegaconf import DictConfig, OmegaConf

from src.core.paths import CONFIGS_DIR, LOGS_DIR
from src.training.data.datamodule import IdeoGraphDataModule
from src.training.models.ideoclassifier import IdeoClassifier


def _resolve_precision(cfg_precision: str) -> str | int:
    """Resuelve `precision: auto` según el accelerator disponible."""
    if cfg_precision != "auto":
        return cfg_precision
    if torch.cuda.is_available():
        major, _ = torch.cuda.get_device_capability()
        return "bf16-mixed" if major >= 8 else "16-mixed"
    if torch.backends.mps.is_available():
        return "32"  # MPS no soporta fp16-mixed estable
    return "32"


def _git_commit_hash() -> str | None:
    """Commit hash actual para trazabilidad."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


@hydra.main(config_path=str(CONFIGS_DIR), config_name="config", version_base=None)
def train(cfg: DictConfig) -> None:
    """Entrena IdeoClassifier con la configuración de Hydra."""

    L.seed_everything(cfg.data.seed, workers=True)

    encoder_model_name = cfg.model.model_name
    encoder_alias = (
        cfg.model.get("encoder_alias_override")
        or cfg.model.get("encoder_alias", "default")
    )

    # --- DataModule (article-level) ---
    datamodule = IdeoGraphDataModule(
        data_path=cfg.data.data_path,
        model_name=encoder_model_name,
        batch_size=cfg.data.batch_size,
        num_workers=cfg.data.num_workers,
        pin_memory=cfg.data.pin_memory,
        val_split=cfg.data.val_split,
        test_split=cfg.data.test_split,
        seed=cfg.data.seed,
        splits_path=cfg.data.get("splits_path", None),
        chunk_size=cfg.data.chunk_size,
        chunk_stride=cfg.data.chunk_stride,
        max_chunks=cfg.data.max_chunks,
        chunking_strategy=cfg.data.chunking_strategy,
    )

    # --- Modelo ---
    model = IdeoClassifier(
        model_name=encoder_model_name,
        num_classes=cfg.model.num_classes,
        dropout=cfg.model.dropout,
        lr=cfg.model.learning_rate,
        weight_decay=cfg.model.weight_decay,
        freeze_encoder_epochs=cfg.model.freeze_encoder_epochs,
        warmup_ratio=cfg.model.get("warmup_ratio", 0.1),
        use_politicity_head=cfg.model.get("use_politicity_head", False),
    )

    # --- Checkpoints ---
    ckpt_dir: Path = LOGS_DIR / "checkpoints" / encoder_alias
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    callbacks = [
        EarlyStopping(
            monitor=cfg.trainer.early_stopping.monitor,
            patience=cfg.trainer.early_stopping.patience,
            mode=cfg.trainer.early_stopping.mode,
        ),
        ModelCheckpoint(
            dirpath=ckpt_dir,
            monitor=cfg.trainer.model_checkpoint.monitor,
            mode=cfg.trainer.model_checkpoint.mode,
            save_top_k=cfg.trainer.model_checkpoint.save_top_k,
            filename=cfg.trainer.model_checkpoint.filename,
        ),
    ]

    precision = _resolve_precision(cfg.trainer.precision)

    trainer = L.Trainer(
        max_epochs=cfg.trainer.max_epochs,
        accelerator=cfg.trainer.accelerator,
        devices=cfg.trainer.devices,
        precision=precision,
        callbacks=callbacks,
        log_every_n_steps=cfg.trainer.log_every_n_steps,
        default_root_dir=str(LOGS_DIR / "lightning_logs" / encoder_alias),
        fast_dev_run=cfg.trainer.get("fast_dev_run", False),
    )

    # --- Training ---
    train_start = time.time()
    trainer.fit(model, datamodule=datamodule)
    train_duration = time.time() - train_start

    if cfg.trainer.get("fast_dev_run", False):
        print("\n[OK] Smoke test completado. No se guardan métricas finales.")
        return

    # --- Test final (OPT-IN — protocolo del anteproyecto) ---
    # La selección de modelo se hace SOLO con validación; el test/gold se
    # toca UNA vez, con el modelo ya elegido (scripts/final_eval.py o
    # run_test=true explícito). El default es False: con True por defecto,
    # cada entrenamiento suelto evaluaba el gold y contaminaba el protocolo.
    run_test = bool(cfg.get("run_test", False))
    test_results = []
    # Métricas de validación del MEJOR checkpoint (las que usa la selección
    # del benchmark y el reporte P2.1).
    # Copia estable del mejor checkpoint: TODA la documentación y
    # final_eval.py referencian logs/checkpoints/<alias>/best.ckpt.
    if trainer.checkpoint_callback and trainer.checkpoint_callback.best_model_path:
        shutil.copyfile(
            trainer.checkpoint_callback.best_model_path, ckpt_dir / "best.ckpt",
        )

    val_results = trainer.validate(model, datamodule=datamodule, ckpt_path="best")
    val_per_class = getattr(model, "val_per_class_final", None)
    val_confmat = getattr(model, "val_confmat_final", None)
    if run_test:
        test_results = trainer.test(model, datamodule=datamodule, ckpt_path="best")

    # --- Recolectar métricas ---
    metrics_dir: Path = LOGS_DIR / "benchmark" / encoder_alias
    metrics_dir.mkdir(parents=True, exist_ok=True)

    # Matriz de confusión y métricas por clase (P2.1) tras el test
    test_confmat = getattr(model, "test_confmat_final", None) if run_test else None
    confmat_serialized = (
        test_confmat.tolist() if test_confmat is not None else None
    )

    best_score = (
        float(trainer.checkpoint_callback.best_model_score)
        if trainer.checkpoint_callback.best_model_score is not None else None
    )
    monitored = cfg.trainer.model_checkpoint.monitor  # ej. "val/f1_macro"

    final_metrics = {
        "encoder_alias": encoder_alias,
        "model_name": encoder_model_name,
        "seed": cfg.data.seed,
        "git_commit": _git_commit_hash(),
        "precision_used": str(precision),
        "train_duration_seconds": train_duration,
        "best_checkpoint": trainer.checkpoint_callback.best_model_path,
        # Métrica monitoreada por el checkpoint (val/f1_macro en la config
        # por defecto). El nombre viejo "best_val_loss" era mentiroso:
        # guardaba el mejor f1_macro. Se conserva como alias deprecado
        # para no romper reportes previos.
        "monitored_metric": monitored,
        "best_val_score": best_score,
        "best_val_loss": best_score,  # DEPRECATED: usar best_val_score
        "ran_test": run_test,
        "val_metrics": val_results[0] if val_results else {},
        "val_per_class": val_per_class,
        "val_confusion_matrix": val_confmat.tolist() if val_confmat is not None else None,
        "test_metrics": test_results[0] if test_results else {},
        "test_per_class": getattr(model, "test_per_class_final", None) if run_test else None,
        "test_confusion_matrix": confmat_serialized,
        "class_names": IdeoClassifier.class_names(),
        "config": OmegaConf.to_container(cfg, resolve=True),
    }

    metrics_path = metrics_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n[OK] Métricas guardadas en: {metrics_path}")


if __name__ == "__main__":
    train()
