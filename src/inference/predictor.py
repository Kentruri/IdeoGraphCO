"""Predictor — carga un checkpoint y clasifica un texto en una de 8 ideologías.

Devuelve la clase predicha + la distribución completa de probabilidades
(que se usa para el mapa de calor).
"""

from __future__ import annotations

from pathlib import Path

import torch
import yaml
from transformers import AutoTokenizer

from src.core.paths import CONFIGS_DIR
from src.core.schema import IDEOLOGY_CLASSES
from src.training.models.ideoclassifier import IdeoClassifier


def _training_chunking_defaults() -> dict:
    """Lee los parámetros de chunking del MISMO YAML que usa el entrenamiento.

    Estaban hardcodeados aquí (`max_chunks=8`) y quedaron desfasados al subir
    el entrenamiento a 16: el modelo se entrenaba viendo hasta el token 6.270
    pero en inferencia solo veía 3.198 — train/serve skew silencioso, y peor
    justo en los artículos largos. Leerlos de la config elimina la deriva.
    """
    defaults = {"chunk_size": 512, "chunk_stride": 384, "max_chunks": 16}
    config_path = CONFIGS_DIR / "data" / "default.yaml"
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except OSError:
        return defaults
    return {k: int(loaded.get(k, v)) for k, v in defaults.items()}


class IdeoClassifierPredictor:
    """Recibe texto plano → clase predicha + probabilidades por clase (%)."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        device: str | None = None,
        chunk_size: int | None = None,
        chunk_stride: int | None = None,
        max_chunks: int | None = None,
    ) -> None:
        if device is None:
            device = (
                "cuda" if torch.cuda.is_available()
                else ("mps" if torch.backends.mps.is_available() else "cpu")
            )
        self.device = torch.device(device)

        self.model = IdeoClassifier.load_from_checkpoint(
            str(checkpoint_path), map_location=self.device,
        )
        self.model.eval()
        self.model.to(self.device)

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model.hparams.model_name,
        )

        # Sin valores explícitos, se toman los del entrenamiento (única
        # fuente de verdad) para que inferencia y entrenamiento troceen igual.
        trained = _training_chunking_defaults()
        self.chunk_size = chunk_size if chunk_size is not None else trained["chunk_size"]
        self.chunk_stride = (
            chunk_stride if chunk_stride is not None else trained["chunk_stride"]
        )
        self.max_chunks = max_chunks if max_chunks is not None else trained["max_chunks"]

        self._cls_id = self.tokenizer.cls_token_id
        self._sep_id = self.tokenizer.sep_token_id
        self._pad_id = self.tokenizer.pad_token_id
        # XLNet coloca <cls> al FINAL de la secuencia. El dataset de
        # entrenamiento lo hace así y el modelo lee esa posición; armar el
        # chunk en orden BERT aquí devolvería el embedding de <sep>.
        self._cls_at_end = "xlnet" in type(self.tokenizer).__name__.lower()

    def _chunk_and_pad(self, text: str) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Devuelve (input_ids, attention_mask, chunk_mask) con shape (1, K, L)."""
        content_length = self.chunk_size - 2
        full_ids = self.tokenizer(
            text, add_special_tokens=False, truncation=False,
        )["input_ids"]

        chunks: list[list[int]] = []
        start = 0
        while start < len(full_ids) and len(chunks) < self.max_chunks:
            end = min(start + content_length, len(full_ids))
            chunks.append(full_ids[start:end])
            if end == len(full_ids):
                break
            start += self.chunk_stride
        if not chunks:
            chunks = [[]]

        input_ids_list: list[list[int]] = []
        attention_list: list[list[int]] = []
        for content in chunks:
            if self._cls_at_end:
                ids = list(content) + [self._sep_id, self._cls_id]
            else:
                ids = [self._cls_id] + list(content) + [self._sep_id]
            mask = [1] * len(ids)
            pad_len = self.chunk_size - len(ids)
            if pad_len > 0:
                ids = ids + [self._pad_id] * pad_len
                mask = mask + [0] * pad_len
            else:
                ids = ids[: self.chunk_size]
                mask = mask[: self.chunk_size]
            input_ids_list.append(ids)
            attention_list.append(mask)

        input_ids = torch.tensor([input_ids_list], dtype=torch.long)      # (1, K, L)
        attention_mask = torch.tensor([attention_list], dtype=torch.long)
        chunk_mask = torch.ones((1, len(chunks)), dtype=torch.long)
        return input_ids, attention_mask, chunk_mask

    @torch.no_grad()
    def predict(self, text: str) -> dict:
        """Predice la ideología dominante de un texto.

        El caller es responsable de garantizar que el texto sea político (por
        ejemplo pasándolo previamente por el filter LLM del scraper).

        Returns:
            {
                "predicted_class": "populismo",
                "confidence": 42.7,                  # porcentaje de la clase ganadora
                "probabilities": {
                    "personalismo": 12.3,
                    "populismo": 42.7,
                    ...
                }
            }
        """
        input_ids, attention_mask, chunk_mask = self._chunk_and_pad(text)
        input_ids = input_ids.to(self.device)
        attention_mask = attention_mask.to(self.device)
        chunk_mask = chunk_mask.to(self.device)

        probs = self.model.predict_proba(input_ids, attention_mask, chunk_mask)
        probs = probs.squeeze(0).cpu().tolist()

        prob_by_class = {
            name: round(p * 100, 2)
            for name, p in zip(IDEOLOGY_CLASSES, probs)
        }
        best_idx = max(range(len(probs)), key=lambda i: probs[i])
        return {
            "predicted_class": IDEOLOGY_CLASSES[best_idx],
            "confidence": round(probs[best_idx] * 100, 2),
            "probabilities": prob_by_class,
        }

    def predict_batch(self, texts: list[str]) -> list[dict]:
        return [self.predict(text) for text in texts]
