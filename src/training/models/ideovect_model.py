"""IdeoVectModel — Multi-output regression con encoder configurable.

Soporta cualquier encoder BERT-compatible (ConfliBERT, BETO, MarIA, etc.)
vía `model_name`. La arquitectura del modelo (8 cabezas) se mantiene igual
entre encoders para que el benchmark sea comparable.

Asume que el dataset es 100% político (filtrado aguas arriba por el LLM
filter del scraper). No incluye cabeza de politicidad.
"""

import lightning as L
import torch
import torch.nn as nn
from torchmetrics.regression import MeanSquaredError, R2Score
from transformers import AutoModel, get_linear_schedule_with_warmup

# Fuente única de los nombres de ejes
from src.core.schema import AXIS_NAMES


class IdeoVectModel(L.LightningModule):
    """Encoder + 8 cabezas MLP independientes para regresión multisalida.

    Flujo:
        input_ids → Encoder → [CLS] embedding → 8 × MLP → Sigmoide → score [0,1]
    """

    def __init__(
        self,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        num_axes: int = 8,
        dropout: float = 0.1,
        lr: float = 2e-5,
        weight_decay: float = 0.01,
        freeze_encoder_epochs: int = 0,
        warmup_ratio: float = 0.1,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        # --- Encoder ---
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size: int = self.encoder.config.hidden_size  # 768 para base, 1024 para large

        # --- 8 Cabezas de Regresión independientes ---
        self.regression_heads = nn.ModuleList([
            nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(hidden_size, 256),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
                nn.Sigmoid(),  # salida en [0, 1]
            )
            for _ in range(num_axes)
        ])

        # --- Loss ---
        self.mse_loss = nn.MSELoss()

        # --- Métricas por eje (separadas para val y test) ---
        self.val_mse = nn.ModuleDict({n: MeanSquaredError() for n in AXIS_NAMES})
        self.val_r2 = nn.ModuleDict({n: R2Score() for n in AXIS_NAMES})
        self.test_mse = nn.ModuleDict({n: MeanSquaredError() for n in AXIS_NAMES})
        self.test_r2 = nn.ModuleDict({n: R2Score() for n in AXIS_NAMES})

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------
    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Retorna axis_scores: (batch, 8) con valores en [0, 1]."""
        cls_hidden = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        ).last_hidden_state[:, 0, :]  # [CLS]

        axis_scores = torch.cat(
            [head(cls_hidden) for head in self.regression_heads],
            dim=-1,
        )  # (batch, 8)
        return axis_scores

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------
    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        axis_scores = self(batch["input_ids"], batch["attention_mask"])
        loss = self.mse_loss(axis_scores, batch["labels"])
        self.log("train/loss", loss, prog_bar=True)
        return loss

    # ------------------------------------------------------------------
    # Eval step (compartido entre validation y test)
    # ------------------------------------------------------------------
    def _eval_step(self, batch: dict, prefix: str) -> None:
        """Evalúa un batch y actualiza métricas para `prefix` ('val' o 'test')."""
        axis_scores = self(batch["input_ids"], batch["attention_mask"])
        loss = self.mse_loss(axis_scores, batch["labels"])

        metric_mse = self.val_mse if prefix == "val" else self.test_mse
        metric_r2 = self.val_r2 if prefix == "val" else self.test_r2
        for i, name in enumerate(AXIS_NAMES):
            metric_mse[name].update(axis_scores[:, i], batch["labels"][:, i])
            metric_r2[name].update(axis_scores[:, i], batch["labels"][:, i])

        self.log(f"{prefix}/loss", loss, prog_bar=(prefix == "val"))

    def _eval_epoch_end(self, prefix: str) -> None:
        """Agrega métricas al final del epoch para `prefix` ('val' o 'test')."""
        metric_mse = self.val_mse if prefix == "val" else self.test_mse
        metric_r2 = self.val_r2 if prefix == "val" else self.test_r2

        for name in AXIS_NAMES:
            self.log(f"{prefix}/mse_{name}", metric_mse[name].compute())
            self.log(f"{prefix}/r2_{name}", metric_r2[name].compute())
            metric_mse[name].reset()
            metric_r2[name].reset()

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validation_step(self, batch: dict, batch_idx: int) -> None:
        self._eval_step(batch, "val")

    def on_validation_epoch_end(self) -> None:
        self._eval_epoch_end("val")

    # ------------------------------------------------------------------
    # Test
    # ------------------------------------------------------------------
    def test_step(self, batch: dict, batch_idx: int) -> None:
        self._eval_step(batch, "test")

    def on_test_epoch_end(self) -> None:
        self._eval_epoch_end("test")

    # ------------------------------------------------------------------
    # Optimizer + Scheduler
    # ------------------------------------------------------------------
    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )

        # Linear warmup + linear decay sobre los pasos totales del entrenamiento.
        # Estándar para fine-tuning de BERT — evita overshoot y mejora estabilidad.
        total_steps = self.trainer.estimated_stepping_batches
        warmup_steps = int(self.hparams.warmup_ratio * total_steps)
        scheduler = get_linear_schedule_with_warmup(
            optimizer,
            num_warmup_steps=warmup_steps,
            num_training_steps=total_steps,
        )

        return {
            "optimizer": optimizer,
            "lr_scheduler": {
                "scheduler": scheduler,
                "interval": "step",
                "frequency": 1,
            },
        }
