"""IdeoClassifier — clasificador multiclase single-label sobre 8 ideologías.

Arquitectura (fiel al anteproyecto):

    Artículo → K chunks de 512 tokens
        ↓
    Encoder (BETO / ConfliBERT / XLM-RoBERTa / ...)
        ↓
    K embeddings [CLS], uno por chunk (shape: (B, K, H))
        ↓
    Agregación V_doc = (1/K) · Σ V_chunk_i (mean-pooling con máscara)
        ↓
    Cabeza lineal 8-way + Softmax implícito (dentro de CrossEntropyLoss)
        ↓
    Distribución P(c | doc) sobre las 8 clases

Loss: Cross-Entropy Categórica.
Métricas: Precision/Recall/F1 Macro, Accuracy, Confusion Matrix.

TBD — Cabeza binaria de politicidad:
    El anteproyecto pide, además del clasificador 8-way, una cabeza binaria
    "¿es política la noticia?". Actualmente NO se implementa porque el filter
    LLM del scraper cumple esta función aguas arriba (ver
    docs/preguntas-director.md tema 1). Si el director requiere fidelidad
    literal al PDF, activar añadiendo `use_politicity_head=True` en el config.
    El código para la cabeza está preparado abajo pero deshabilitado.
"""

from __future__ import annotations

import pytorch_lightning as L
import torch
import torch.nn as nn
import torch.nn.functional as F
from torchmetrics.classification import (
    MulticlassAccuracy,
    MulticlassConfusionMatrix,
    MulticlassF1Score,
    MulticlassPrecision,
    MulticlassRecall,
)
from transformers import AutoModel, get_linear_schedule_with_warmup

from src.core.schema import IDEOLOGY_CLASSES, NUM_CLASSES


class IdeoClassifier(L.LightningModule):
    """Encoder + agregación mean-pool + cabeza softmax 8-way."""

    def __init__(
        self,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        num_classes: int = NUM_CLASSES,
        dropout: float = 0.1,
        lr: float = 2e-5,
        weight_decay: float = 0.01,
        freeze_encoder_epochs: int = 0,
        warmup_ratio: float = 0.1,
        use_politicity_head: bool = False,  # TBD — ver docstring del módulo
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        # --- Encoder ---
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden_size: int = self.encoder.config.hidden_size

        # --- Cabeza de clasificación ideológica (8-way) ---
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_classes)

        # --- Cabeza binaria de politicidad (deshabilitada por defecto) ---
        # Ver TBD en el docstring del módulo.
        self.politicity_head: nn.Linear | None = None
        if use_politicity_head:
            self.politicity_head = nn.Linear(hidden_size, 2)

        # --- Métricas (separadas por split para no mezclar acumuladores) ---
        self.val_metrics = self._build_metric_bundle("val")
        self.test_metrics = self._build_metric_bundle("test")
        self.val_confmat = MulticlassConfusionMatrix(num_classes=num_classes)
        self.test_confmat = MulticlassConfusionMatrix(num_classes=num_classes)

    def _build_metric_bundle(self, prefix: str) -> nn.ModuleDict:
        """Bundle de métricas macro (Precision, Recall, F1) + Accuracy."""
        return nn.ModuleDict({
            "precision_macro": MulticlassPrecision(
                num_classes=NUM_CLASSES, average="macro"
            ),
            "recall_macro": MulticlassRecall(
                num_classes=NUM_CLASSES, average="macro"
            ),
            "f1_macro": MulticlassF1Score(
                num_classes=NUM_CLASSES, average="macro"
            ),
            "accuracy": MulticlassAccuracy(
                num_classes=NUM_CLASSES, average="micro"
            ),
        })

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------
    def forward(
        self,
        input_ids: torch.Tensor,        # (B, K, L)
        attention_mask: torch.Tensor,   # (B, K, L)
        chunk_mask: torch.Tensor,       # (B, K)  1=chunk real, 0=padding
    ) -> torch.Tensor:
        """Retorna logits (B, num_classes).

        Aplana los K chunks para pasarlos por el encoder en una sola llamada,
        luego reagrupa por artículo y promedia (V_doc = mean V_chunk_i).
        """
        B, K, L = input_ids.shape

        # Aplanar (B*K, L) para pasar por el encoder en batch único
        flat_ids = input_ids.reshape(B * K, L)
        flat_mask = attention_mask.reshape(B * K, L)

        # [CLS] embedding de cada chunk: (B*K, H)
        cls_emb = self.encoder(
            input_ids=flat_ids,
            attention_mask=flat_mask,
        ).last_hidden_state[:, 0, :]

        # Reagrupar por artículo: (B, K, H)
        cls_emb = cls_emb.reshape(B, K, -1)

        # Agregación V_doc = mean sobre chunks REALES (ignorando padding)
        # chunk_mask: (B, K)  → (B, K, 1) para broadcast
        cm = chunk_mask.unsqueeze(-1).float()
        masked_sum = (cls_emb * cm).sum(dim=1)                # (B, H)
        n_chunks = cm.sum(dim=1).clamp(min=1.0)               # (B, 1)
        doc_emb = masked_sum / n_chunks                       # (B, H)

        # Dropout + cabeza lineal → logits (softmax implícito en CE loss)
        logits = self.classifier(self.dropout(doc_emb))       # (B, num_classes)
        return logits

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------
    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        logits = self(
            batch["input_ids"],
            batch["attention_mask"],
            batch["chunk_mask"],
        )
        loss = F.cross_entropy(logits, batch["labels"])
        self.log("train/loss", loss, prog_bar=True)
        return loss

    # ------------------------------------------------------------------
    # Eval (validation + test)
    # ------------------------------------------------------------------
    def _eval_step(self, batch: dict, prefix: str) -> None:
        logits = self(
            batch["input_ids"],
            batch["attention_mask"],
            batch["chunk_mask"],
        )
        loss = F.cross_entropy(logits, batch["labels"])
        preds = logits.argmax(dim=-1)
        labels = batch["labels"]

        metrics = self.val_metrics if prefix == "val" else self.test_metrics
        for m in metrics.values():
            m.update(preds, labels)
        confmat = self.val_confmat if prefix == "val" else self.test_confmat
        confmat.update(preds, labels)

        self.log(f"{prefix}/loss", loss, prog_bar=(prefix == "val"))

    def _eval_epoch_end(self, prefix: str) -> None:
        metrics = self.val_metrics if prefix == "val" else self.test_metrics
        confmat = self.val_confmat if prefix == "val" else self.test_confmat

        for name, m in metrics.items():
            self.log(f"{prefix}/{name}", m.compute(), prog_bar=(name == "f1_macro"))
            m.reset()

        # La matriz de confusión no se loguea a escalar; se puede recuperar en
        # callbacks/tests explícitos. Guardarla como atributo para acceso post-fit.
        confmat_final = confmat.compute().detach().cpu()
        setattr(self, f"{prefix}_confmat_final", confmat_final)
        # Métricas POR CLASE (P2.1 del anteproyecto), derivadas de la matriz
        # de confusión: filas = clase real, columnas = predicha.
        setattr(
            self,
            f"{prefix}_per_class_final",
            self._per_class_from_confmat(confmat_final),
        )
        confmat.reset()

    @staticmethod
    def _per_class_from_confmat(confmat: torch.Tensor) -> dict[str, dict[str, float]]:
        """Precision/Recall/F1/support por clase desde la matriz de confusión."""
        per_class: dict[str, dict[str, float]] = {}
        for i, cls in enumerate(IDEOLOGY_CLASSES[: confmat.shape[0]]):
            tp = confmat[i, i].item()
            support = confmat[i, :].sum().item()
            predicted = confmat[:, i].sum().item()
            precision = tp / predicted if predicted > 0 else 0.0
            recall = tp / support if support > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0 else 0.0
            )
            per_class[cls] = {
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(f1, 4),
                "support": int(support),
            }
        return per_class

    def validation_step(self, batch: dict, batch_idx: int) -> None:
        self._eval_step(batch, "val")

    def on_validation_epoch_end(self) -> None:
        self._eval_epoch_end("val")

    def test_step(self, batch: dict, batch_idx: int) -> None:
        self._eval_step(batch, "test")

    def on_test_epoch_end(self) -> None:
        self._eval_epoch_end("test")

    # ------------------------------------------------------------------
    # Optimizer + scheduler
    # ------------------------------------------------------------------
    def configure_optimizers(self):
        optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=self.hparams.lr,
            weight_decay=self.hparams.weight_decay,
        )
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

    # ------------------------------------------------------------------
    # Helpers para predictor / inferencia
    # ------------------------------------------------------------------
    @torch.no_grad()
    def predict_proba(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        chunk_mask: torch.Tensor,
    ) -> torch.Tensor:
        """Devuelve probabilidades (B, num_classes) para uso en inferencia."""
        logits = self(input_ids, attention_mask, chunk_mask)
        return F.softmax(logits, dim=-1)

    @staticmethod
    def class_names() -> list[str]:
        """Nombres canónicos de las 8 clases en el orden de las columnas de logits."""
        return list(IDEOLOGY_CLASSES)
