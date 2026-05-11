"""IdeoVectModel — Multi-output regression con encoder configurable.

Soporta cualquier encoder BERT-compatible (ConfliBERT, BETO, MarIA, etc.)
vía `model_name`. La arquitectura del modelo (8 cabezas + filtro opcional)
se mantiene igual entre encoders para que el benchmark sea comparable.
"""

import lightning as L
import torch
import torch.nn as nn
from torchmetrics.regression import MeanSquaredError, R2Score
from transformers import AutoModel, get_linear_schedule_with_warmup


# Los 8 ejes ideológicos en orden canónico — fuente de verdad
AXIS_NAMES: list[str] = [
    "personalismo",
    "institucionalismo",
    "populismo",
    "doctrinarismo",
    "soberanismo",
    "globalismo",
    "conservadurismo",
    "progresismo",
]


class IdeoVectModel(L.LightningModule):
    """Encoder configurable + filtro de politicidad opcional + 8 cabezas de regresión.

    Flujo:
        input_ids → Encoder → [CLS] embedding
                                ├─→ Filtro de politicidad (opcional)
                                └─→ 8 × MLP → Sigmoide → score [0, 1]
    """

    def __init__(
        self,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        num_axes: int = 8,
        dropout: float = 0.1,
        lr: float = 2e-5,
        weight_decay: float = 0.01,
        freeze_encoder_epochs: int = 0,
        use_politicity_head: bool = False,
        warmup_ratio: float = 0.1,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        # --- Encoder ---
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size: int = self.encoder.config.hidden_size  # 768 para base, 1024 para large

        # --- Filtro de Politicidad (opcional) ---
        # Cuando todos los artículos del dataset son políticos (is_political=1),
        # esta cabeza converge a una solución trivial y solo añade ruido al encoder.
        # Apagarla con use_politicity_head=False mejora la comparación del benchmark.
        self.politicity_head: nn.Sequential | None
        if use_politicity_head:
            self.politicity_head = nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(hidden_size, 2),
            )
        else:
            self.politicity_head = None

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

        # --- Losses ---
        self.ce_loss = nn.CrossEntropyLoss()
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
    ) -> tuple[torch.Tensor | None, torch.Tensor]:
        """Retorna (politicity_logits | None, axis_scores).

        axis_scores: (batch, 8) con valores en [0, 1].
        politicity_logits: (batch, 2) si use_politicity_head=True, None si no.
        """
        cls_hidden = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        ).last_hidden_state[:, 0, :]  # [CLS]

        politicity_logits = (
            self.politicity_head(cls_hidden) if self.politicity_head is not None else None
        )

        axis_scores = torch.cat(
            [head(cls_hidden) for head in self.regression_heads],
            dim=-1,
        )  # (batch, 8)

        return politicity_logits, axis_scores

    # ------------------------------------------------------------------
    # Training step
    # ------------------------------------------------------------------
    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        politicity_logits, axis_scores = self(
            batch["input_ids"], batch["attention_mask"],
        )

        # Loss de regresión (solo para noticias políticas)
        mask = batch["is_political"].bool()
        if mask.any():
            loss_reg = self.mse_loss(axis_scores[mask], batch["labels"][mask])
        else:
            loss_reg = torch.tensor(0.0, device=self.device)

        # Loss de politicidad (si la cabeza está activa)
        if politicity_logits is not None:
            loss_pol = self.ce_loss(politicity_logits, batch["is_political"])
            total_loss = loss_pol + loss_reg
            self.log("train/loss_pol", loss_pol)
        else:
            total_loss = loss_reg

        self.log("train/loss", total_loss, prog_bar=True)
        self.log("train/loss_reg", loss_reg)
        return total_loss

    # ------------------------------------------------------------------
    # Eval step (compartido entre validation y test)
    # ------------------------------------------------------------------
    def _eval_step(self, batch: dict, prefix: str) -> None:
        """Evalúa un batch y actualiza métricas para `prefix` ('val' o 'test')."""
        politicity_logits, axis_scores = self(
            batch["input_ids"], batch["attention_mask"],
        )

        mask = batch["is_political"].bool()
        if mask.any():
            loss_reg = self.mse_loss(axis_scores[mask], batch["labels"][mask])
            preds = axis_scores[mask]
            targets = batch["labels"][mask]

            metric_mse = self.val_mse if prefix == "val" else self.test_mse
            metric_r2 = self.val_r2 if prefix == "val" else self.test_r2
            for i, name in enumerate(AXIS_NAMES):
                metric_mse[name].update(preds[:, i], targets[:, i])
                metric_r2[name].update(preds[:, i], targets[:, i])
        else:
            loss_reg = torch.tensor(0.0, device=self.device)

        if politicity_logits is not None:
            loss_pol = self.ce_loss(politicity_logits, batch["is_political"])
            total = loss_pol + loss_reg
            self.log(f"{prefix}/loss_pol", loss_pol)
        else:
            total = loss_reg

        self.log(f"{prefix}/loss", total, prog_bar=(prefix == "val"))
        self.log(f"{prefix}/loss_reg", loss_reg)

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
