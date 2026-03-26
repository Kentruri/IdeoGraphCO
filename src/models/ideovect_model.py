"""IdeoVectModel — Multi-output regression con ConfliBERT-Spanish."""

import lightning as L
import torch
import torch.nn as nn
from torchmetrics.regression import MeanSquaredError, R2Score
from transformers import AutoModel


# Los 8 ejes ideológicos en orden canónico
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
    """ConfliBERT-Spanish + filtro de politicidad + 8 cabezas de regresión.

    Flujo:
        input_ids → ConfliBERT → [CLS] embedding (768)
                                    ├─→ Filtro de politicidad (binario)
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
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        # --- Encoder ---
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size: int = self.encoder.config.hidden_size  # 768

        # --- Filtro de Politicidad (gate binario) ---
        self.politicity_head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size, 2),  # político / no-político
        )

        # --- 8 Cabezas de Regresión independientes ---
        self.regression_heads = nn.ModuleList([
            nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(hidden_size, 256),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(256, 1),
                nn.Sigmoid(),  # salida en [0, 1], escalar a 0-100 en inferencia
            )
            for _ in range(num_axes)
        ])

        # --- Losses ---
        self.ce_loss = nn.CrossEntropyLoss()
        self.mse_loss = nn.MSELoss()

        # --- Métricas por eje ---
        self.val_mse = nn.ModuleDict({
            name: MeanSquaredError() for name in AXIS_NAMES
        })
        self.val_r2 = nn.ModuleDict({
            name: R2Score() for name in AXIS_NAMES
        })

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------
    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Retorna (politicity_logits, axis_scores).

        axis_scores: (batch, 8) con valores en [0, 1].
        """
        cls_hidden = self.encoder(
            input_ids=input_ids,
            attention_mask=attention_mask,
        ).last_hidden_state[:, 0, :]  # [CLS]

        politicity_logits = self.politicity_head(cls_hidden)

        axis_scores = torch.cat(
            [head(cls_hidden) for head in self.regression_heads],
            dim=-1,
        )  # (batch, 8)

        return politicity_logits, axis_scores

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        politicity_logits, axis_scores = self(
            batch["input_ids"], batch["attention_mask"],
        )

        # Loss de politicidad (clasificación binaria)
        loss_pol = self.ce_loss(politicity_logits, batch["is_political"])

        # Loss de regresión (solo para noticias políticas)
        mask = batch["is_political"].bool()
        if mask.any():
            loss_reg = self.mse_loss(
                axis_scores[mask], batch["labels"][mask],
            )
        else:
            loss_reg = torch.tensor(0.0, device=self.device)

        total_loss = loss_pol + loss_reg

        self.log("train/loss", total_loss, prog_bar=True)
        self.log("train/loss_pol", loss_pol)
        self.log("train/loss_reg", loss_reg)

        return total_loss

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def validation_step(self, batch: dict, batch_idx: int) -> None:
        politicity_logits, axis_scores = self(
            batch["input_ids"], batch["attention_mask"],
        )

        loss_pol = self.ce_loss(politicity_logits, batch["is_political"])

        mask = batch["is_political"].bool()
        if mask.any():
            loss_reg = self.mse_loss(
                axis_scores[mask], batch["labels"][mask],
            )
            # Métricas por eje
            preds = axis_scores[mask]
            targets = batch["labels"][mask]
            for i, name in enumerate(AXIS_NAMES):
                self.val_mse[name].update(preds[:, i], targets[:, i])
                self.val_r2[name].update(preds[:, i], targets[:, i])
        else:
            loss_reg = torch.tensor(0.0, device=self.device)

        self.log("val/loss", loss_pol + loss_reg, prog_bar=True)

    def on_validation_epoch_end(self) -> None:
        for name in AXIS_NAMES:
            self.log(f"val/mse_{name}", self.val_mse[name].compute())
            self.log(f"val/r2_{name}", self.val_r2[name].compute())
            self.val_mse[name].reset()
            self.val_r2[name].reset()

    # ------------------------------------------------------------------
    # Optimizer
    # ------------------------------------------------------------------
    def configure_optimizers(self) -> torch.optim.Optimizer:
        return torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )
