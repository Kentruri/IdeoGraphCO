"""Script principal de entrenamiento — conecta Hydra + Lightning + IdeoVectModel.

Usa el `model_name` definido en `configs/model/*.yaml` tanto para el encoder
como para el tokenizer (consistencia entre modelo y datos).

Al terminar, guarda métricas finales en `logs/benchmark/<encoder_alias>/metrics.json`
para que el script de benchmark/compare_models las pueda recolectar.
"""

import json
import time
from pathlib import Path

import hydra
import lightning as L
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from omegaconf import DictConfig, OmegaConf

from src.data.datamodule import IdeoGraphDataModule
from src.models.ideovect_model import IdeoVectModel
from src.paths import CONFIGS_DIR, LOGS_DIR


@hydra.main(config_path=str(CONFIGS_DIR), config_name="config", version_base=None)
def train(cfg: DictConfig) -> None:
    """Entrena IdeoVectModel con la configuración de Hydra."""

    L.seed_everything(cfg.data.seed, workers=True)

    # Propagar model_name del modelo al tokenizer (garantizar consistencia)
    encoder_model_name = cfg.model.model_name
    encoder_alias = cfg.model.get("encoder_alias", "default")

    # --- DataModule (usa el mismo model_name para el tokenizer) ---
    datamodule = IdeoGraphDataModule(
        data_path=cfg.data.data_path,
        model_name=encoder_model_name,
        max_length=cfg.data.max_length,
        batch_size=cfg.data.batch_size,
        num_workers=cfg.data.num_workers,
        pin_memory=cfg.data.pin_memory,
        val_split=cfg.data.val_split,
        test_split=cfg.data.test_split,
        seed=cfg.data.seed,
    )

    # --- Modelo ---
    model = IdeoVectModel(
        model_name=encoder_model_name,
        num_axes=cfg.model.num_axes,
        dropout=cfg.model.dropout,
        lr=cfg.model.learning_rate,
        weight_decay=cfg.model.weight_decay,
        freeze_encoder_epochs=cfg.model.freeze_encoder_epochs,
    )

    # --- Directorio de checkpoints separado por encoder ---
    ckpt_dir: Path = LOGS_DIR / "checkpoints" / encoder_alias
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # --- Callbacks ---
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

    # --- Trainer ---
    trainer = L.Trainer(
        max_epochs=cfg.trainer.max_epochs,
        accelerator=cfg.trainer.accelerator,
        devices=cfg.trainer.devices,
        precision=cfg.trainer.precision,
        callbacks=callbacks,
        log_every_n_steps=cfg.trainer.log_every_n_steps,
        default_root_dir=str(LOGS_DIR / "lightning_logs" / encoder_alias),
    )

    # --- Entrenamiento ---
    train_start = time.time()
    trainer.fit(model, datamodule=datamodule)
    train_duration = time.time() - train_start

    # --- Test final ---
    test_results = trainer.test(model, datamodule=datamodule, ckpt_path="best")

    # --- Recolectar métricas finales ---
    metrics_dir: Path = LOGS_DIR / "benchmark" / encoder_alias
    metrics_dir.mkdir(parents=True, exist_ok=True)

    final_metrics = {
        "encoder_alias": encoder_alias,
        "model_name": encoder_model_name,
        "train_duration_seconds": train_duration,
        "best_checkpoint": trainer.checkpoint_callback.best_model_path,
        "best_val_loss": float(trainer.checkpoint_callback.best_model_score)
        if trainer.checkpoint_callback.best_model_score is not None else None,
        "test_metrics": test_results[0] if test_results else {},
        "config": OmegaConf.to_container(cfg, resolve=True),
    }

    metrics_path = metrics_dir / "metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(final_metrics, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Métricas guardadas en: {metrics_path}")


if __name__ == "__main__":
    train()
