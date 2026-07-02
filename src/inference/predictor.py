"""Predictor — carga un checkpoint y clasifica un texto en una de 8 ideologías.

Devuelve la clase predicha + la distribución completa de probabilidades
(que se usa para el mapa de calor).
"""

from __future__ import annotations

from pathlib import Path

import torch
from transformers import AutoTokenizer

from src.core.schema import IDEOLOGY_CLASSES
from src.training.models.ideoclassifier import IdeoClassifier


class IdeoClassifierPredictor:
    """Recibe texto plano → clase predicha + probabilidades por clase (%)."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        device: str | None = None,
        chunk_size: int = 512,
        chunk_stride: int = 384,
        max_chunks: int = 8,
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

        self.chunk_size = chunk_size
        self.chunk_stride = chunk_stride
        self.max_chunks = max_chunks

        self._cls_id = self.tokenizer.cls_token_id
        self._sep_id = self.tokenizer.sep_token_id
        self._pad_id = self.tokenizer.pad_token_id

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
            ids = [self._cls_id] + content + [self._sep_id]
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
