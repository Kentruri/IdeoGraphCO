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


def _checkpoint_layers(encoder: nn.Module) -> None:
    """Gradient checkpointing capa a capa para encoders que no lo traen.

    Mismo mecanismo que `gradient_checkpointing_enable` de transformers:
    cada capa se recalcula en el backward. `use_reentrant=False` admite los
    kwargs y los `None` de la firma de XLNetLayer, y el estado del RNG se
    preserva, así que el dropout del recálculo coincide con el del forward.
    """
    layers = getattr(encoder, "layer", None)
    if not isinstance(layers, nn.ModuleList):
        raise ValueError(
            f"{type(encoder).__name__}: no hay gradient checkpointing nativo ni "
            "una lista de capas `.layer` que envolver."
        )
    from torch.utils.checkpoint import checkpoint

    for layer in layers:
        original = layer.forward

        def forward(*args, _orig=original, _layer=layer, **kwargs):
            if _layer.training and torch.is_grad_enabled():
                return checkpoint(_orig, *args, use_reentrant=False, **kwargs)
            return _orig(*args, **kwargs)

        layer.forward = forward


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
        chunk_size: int = 512,
        chunk_stride: int = 384,
        max_chunks: int = 16,
        class_weights: list[float] | None = None,
        gradient_checkpointing: bool = False,
    ) -> None:
        super().__init__()
        # El troceo es de DATOS, no del modelo, pero viaja en los
        # hiperparámetros a propósito: el checkpoint tiene que describirse a sí
        # mismo. Quien sirva el modelo (IdeoGraphCO-BE) no tiene
        # configs/data/default.yaml, y si adivina los valores reaparece el
        # train/serve skew que ya ocurrió una vez (entrenar con max_chunks=16
        # y servir con 8: el modelo veía hasta el token 6.270 al entrenar y
        # 3.198 al predecir, peor cuanto más largo el artículo).
        self.save_hyperparameters()

        # --- Encoder ---
        self.encoder = AutoModel.from_pretrained(model_name)
        # from_pretrained devuelve el encoder en modo eval, y Lightning ≥2.3
        # respeta el modo de cada submódulo al empezar el fit (ya no llama a
        # .train()): sin esto el dropout interno del encoder quedaba apagado
        # durante todo el entrenamiento.
        self.encoder.train()
        if gradient_checkpointing:
            # Recalcula las activaciones del encoder en el backward en vez de
            # guardarlas: ~30 % más lento y mismo resultado, pero un batch con
            # artículos largos (hasta 8 × 16 chunks de 512) cabe en la GPU de
            # un portátil.
            if getattr(self.encoder, "supports_gradient_checkpointing", False):
                self.encoder.gradient_checkpointing_enable(
                    gradient_checkpointing_kwargs={"use_reentrant": False},
                )
            else:
                # XLNet no lo trae en transformers: sin esto pedía ~26 GB con
                # batch 1 × 16 y en un Mac de 24 GB se arrastraba en swap
                # (~7 h por época). Se envuelve cada capa a mano.
                _checkpoint_layers(self.encoder)
        hidden_size: int = self.encoder.config.hidden_size
        # XLNet lleva <cls> al FINAL de la secuencia; el dataset arma los
        # chunks en ese orden (misma detección, vía el nombre del tokenizer).
        self._cls_at_end: bool = self.encoder.config.model_type == "xlnet"

        # --- Cabeza de clasificación ideológica (8-way) ---
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(hidden_size, num_classes)

        # --- Cabeza binaria de politicidad (deshabilitada por defecto) ---
        # Ver TBD en el docstring del módulo.
        self.politicity_head: nn.Linear | None = None
        if use_politicity_head:
            self.politicity_head = nn.Linear(hidden_size, 2)

        # --- Pesos por clase de la pérdida (src/training/class_weights.py) ---
        # Solo pesan en ENTRENAMIENTO: la pérdida de validación queda sin
        # ponderar para que siga comparándose entre corridas, y la selección
        # de modelo va por f1_macro de todos modos. No persiste en el
        # state_dict: viaja en los hiperparámetros, como el troceo.
        self.register_buffer(
            "loss_weights",
            torch.tensor(class_weights, dtype=torch.float) if class_weights else None,
            persistent=False,
        )

        # --- Métricas (separadas por split para no mezclar acumuladores) ---
        self.val_metrics = self._build_metric_bundle("val")
        self.test_metrics = self._build_metric_bundle("test")
        self.val_confmat = MulticlassConfusionMatrix(num_classes=num_classes)
        self.test_confmat = MulticlassConfusionMatrix(num_classes=num_classes)

    def on_train_epoch_start(self) -> None:
        """Congela el encoder las primeras `freeze_encoder_epochs` épocas.

        El parámetro existía en todos los configs pero era un no-op
        silencioso; ahora entrena solo la cabeza durante el warmup y
        descongela después.
        """
        n_freeze = int(self.hparams.get("freeze_encoder_epochs", 0) or 0)
        if n_freeze <= 0:
            return
        freeze = self.current_epoch < n_freeze
        for param in self.encoder.parameters():
            param.requires_grad = not freeze
        if self.current_epoch == n_freeze:
            self.print(f"Encoder descongelado en la época {self.current_epoch}")

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

        # Aplanar (B*K, L) y pasar por el encoder SOLO los chunks reales: el
        # collate rellena cada artículo hasta el K mayor del batch, y esos
        # chunks vacíos costaban lo mismo que los reales (un artículo de 16
        # chunks convertía un batch de 8 en 128 secuencias de 512). Su
        # embedding se descartaba igual por chunk_mask, así que el resultado
        # no cambia.
        flat_ids = input_ids.reshape(B * K, L)
        flat_mask = attention_mask.reshape(B * K, L)
        real = chunk_mask.reshape(B * K).nonzero(as_tuple=True)[0]
        # El dataset rellena cada chunk a la derecha hasta chunk_size; se
        # recorta hasta el chunk real más largo. El relleno está enmascarado,
        # así que la salida no cambia, pero con un encoder de contexto largo
        # (chunk_size 8192) un artículo típico de ~900 tokens dejaba de
        # costar como uno de 8192.
        # El ancho se redondea a múltiplos de 256: con un ancho distinto en
        # cada batch, el allocator de MPS acumulaba bloques de cada tamaño sin
        # reutilizarlos (10,7 GB "reservados" para 5 GB reales con MrBERT-es).
        real_mask = flat_mask[real]
        width = int(real_mask.sum(dim=1).max())
        width = min(L, -(-width // 256) * 256)
        real_mask = real_mask[:, :width]

        # [CLS] embedding de cada chunk real: (R, H)
        hidden = self.encoder(
            input_ids=flat_ids[real, :width],
            attention_mask=real_mask,
        ).last_hidden_state
        if self._cls_at_end:
            # <cls> es el último token real (padding a la derecha): indexar
            # por longitud real de cada chunk.
            idx = real_mask.sum(dim=1).clamp(min=1) - 1
            rows = torch.arange(hidden.size(0), device=hidden.device)
            real_cls = hidden[rows, idx, :]
        else:
            real_cls = hidden[:, 0, :]

        # Reagrupar por artículo: (B, K, H); los chunks de relleno quedan en 0
        cls_emb = real_cls.new_zeros(B * K, real_cls.size(-1)).index_copy(0, real, real_cls)
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
    def on_train_batch_end(self, outputs, batch: dict, batch_idx: int) -> None:
        # En MPS el allocator no devuelve los bloques cacheados hasta llegar al
        # tope; con artículos de largo variable eso acaba en OOM a mitad de
        # época. Vaciar la caché cada 50 batches cuesta poco y lo evita.
        if self.device.type == "mps" and batch_idx % 50 == 0:
            torch.mps.empty_cache()

    def training_step(self, batch: dict, batch_idx: int) -> torch.Tensor:
        logits = self(
            batch["input_ids"],
            batch["attention_mask"],
            batch["chunk_mask"],
        )
        loss = F.cross_entropy(logits, batch["labels"], weight=self.loss_weights)
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
