"""Script principal de entrenamiento — conecta Hydra + Lightning + IdeoVectModel."""

import hydra
import lightning as L
from lightning.pytorch.callbacks import EarlyStopping, ModelCheckpoint
from omegaconf import DictConfig

from src.data.datamodule import IdeoGraphDataModule
from src.models.ideovect_model import IdeoVectModel
from src.paths import CONFIGS_DIR, LOGS_DIR


@hydra.main(config_path=str(CONFIGS_DIR), config_name="config", version_base=None)
def train(cfg: DictConfig) -> None:
    """Entrena IdeoVectModel con la configuración de Hydra."""

    L.seed_everything(cfg.data.seed, workers=True)

    # --- DataModule ---
    datamodule = IdeoGraphDataModule(
        data_path=cfg.data.data_path,
        model_name=cfg.data.model_name,
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
        model_name=cfg.model.model_name,
        num_axes=cfg.model.num_axes,
        dropout=cfg.model.dropout,
        lr=cfg.model.learning_rate,
        weight_decay=cfg.model.weight_decay,
        freeze_encoder_epochs=cfg.model.freeze_encoder_epochs,
    )

    # --- Callbacks ---
    callbacks = [
        EarlyStopping(
            monitor=cfg.trainer.early_stopping.monitor,
            patience=cfg.trainer.early_stopping.patience,
            mode=cfg.trainer.early_stopping.mode,
        ),
        ModelCheckpoint(
            dirpath=LOGS_DIR / "checkpoints",
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
        default_root_dir=str(LOGS_DIR),
    )

    # --- Entrenamiento ---
    trainer.fit(model, datamodule=datamodule)

    # --- Test final ---
    trainer.test(model, datamodule=datamodule, ckpt_path="best")


if __name__ == "__main__":
    train()
