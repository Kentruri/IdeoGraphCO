"""Dataset para noticias colombianas con etiquetas ideológicas de 8 ejes.

Soporta dos estrategias para manejar textos más largos que `max_length`:

1. **truncate** (default, rápido): trunca el texto al primer `max_length` tokens.
   Pierde contenido pero es estándar para BERT.

2. **sliding_window** (recomendado para artículos largos): divide cada artículo
   en chunks superpuestos. Cada chunk se trata como una muestra independiente
   con los mismos labels del artículo original. La agregación de predicciones
   por artículo se hace en el modelo (en validation/test).
"""

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer

from src.models.ideovect_model import AXIS_NAMES


class IdeoGraphDataset(Dataset):
    """Carga noticias etiquetadas y las tokeniza con soporte de sliding window.

    Cada elemento del dataset es un *chunk* (no un artículo). Para `truncate`,
    cada artículo produce 1 chunk. Para `sliding_window`, un artículo largo
    produce N chunks que comparten los mismos labels.

    Formato esperado del JSONL:
        {
            "text": "El presidente anunció...",
            "is_political": 1,
            "personalismo": 0.72,
            "institucionalismo": 0.15,
            ...
        }
    """

    def __init__(
        self,
        data_path: Path,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        max_length: int = 512,
        chunking_strategy: str = "truncate",  # "truncate" | "sliding_window"
        chunk_size: int = 512,
        chunk_stride: int = 384,  # 25% de overlap
    ) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.max_length = max_length
        self.chunking_strategy = chunking_strategy
        self.chunk_size = chunk_size
        self.chunk_stride = chunk_stride

        # Carga de artículos (lista cruda del JSONL)
        self.articles: list[dict] = self._load(data_path)

        # Pre-computar chunks: cada entrada es (article_idx, token_ids o None)
        # Si "tokens" es None → estrategia truncate (se tokeniza on-the-fly)
        # Si "tokens" tiene valor → estrategia sliding_window (ya pre-tokenizado)
        self.chunks: list[dict] = self._compute_chunks()

    @staticmethod
    def _load(path: Path) -> list[dict]:
        """Lee un archivo JSONL."""
        samples: list[dict] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    samples.append(json.loads(line))
        return samples

    def _compute_chunks(self) -> list[dict]:
        """Pre-computa los chunks según la estrategia de chunking."""
        if self.chunking_strategy == "truncate":
            # 1 chunk por artículo. Tokenización lazy en __getitem__.
            return [
                {"article_idx": i, "chunk_idx_in_article": 0, "tokens": None}
                for i in range(len(self.articles))
            ]

        if self.chunking_strategy == "sliding_window":
            return self._sliding_window_chunks()

        raise ValueError(
            f"chunking_strategy desconocida: {self.chunking_strategy}. "
            "Usa 'truncate' o 'sliding_window'."
        )

    def _sliding_window_chunks(self) -> list[dict]:
        """Genera chunks de longitud fija con overlap por cada artículo.

        Pre-tokeniza todos los artículos (más rápido que tokenizar en cada
        __getitem__), guarda los ids y los slicea según chunk_size + stride.
        """
        chunks: list[dict] = []
        # Tokens especiales del tokenizer (CLS, SEP) reservan 2 posiciones
        # → el contenido real por chunk es chunk_size - 2
        content_length = self.chunk_size - 2

        cls_id = self.tokenizer.cls_token_id
        sep_id = self.tokenizer.sep_token_id

        for art_idx, article in enumerate(self.articles):
            # Tokenizar sin truncation ni padding, solo IDs sin especiales
            full_ids = self.tokenizer(
                article["text"],
                add_special_tokens=False,
                truncation=False,
            )["input_ids"]

            # Si el artículo cabe entero, un solo chunk
            if len(full_ids) <= content_length:
                chunks.append({
                    "article_idx": art_idx,
                    "chunk_idx_in_article": 0,
                    "tokens": full_ids,
                })
                continue

            # Sliding window con stride
            start = 0
            chunk_idx = 0
            while start < len(full_ids):
                end = min(start + content_length, len(full_ids))
                chunks.append({
                    "article_idx": art_idx,
                    "chunk_idx_in_article": chunk_idx,
                    "tokens": full_ids[start:end],
                })
                chunk_idx += 1
                if end == len(full_ids):
                    break
                start += self.chunk_stride

        # Guardar IDs especiales para __getitem__
        self._cls_id = cls_id
        self._sep_id = sep_id
        self._pad_id = self.tokenizer.pad_token_id
        return chunks

    def __len__(self) -> int:
        return len(self.chunks)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        chunk = self.chunks[idx]
        article = self.articles[chunk["article_idx"]]

        if self.chunking_strategy == "truncate" or chunk["tokens"] is None:
            # Tokenización on-the-fly con truncation y padding
            encoding = self.tokenizer(
                article["text"],
                max_length=self.max_length,
                padding="max_length",
                truncation=True,
                return_tensors="pt",
            )
            input_ids = encoding["input_ids"].squeeze(0)
            attention_mask = encoding["attention_mask"].squeeze(0)
        else:
            # Sliding window: envolver tokens en [CLS] ... [SEP] y padear
            content = chunk["tokens"]
            ids = [self._cls_id] + content + [self._sep_id]
            mask = [1] * len(ids)
            # Padding al chunk_size
            pad_len = self.chunk_size - len(ids)
            ids = ids + [self._pad_id] * pad_len
            mask = mask + [0] * pad_len
            input_ids = torch.tensor(ids[:self.chunk_size], dtype=torch.long)
            attention_mask = torch.tensor(mask[:self.chunk_size], dtype=torch.long)

        # Etiquetas de los 8 ejes (en orden canónico).
        # Soporta dos formatos: scores en root o anidados en "labels".
        nested = article.get("labels", {})
        labels = torch.tensor(
            [
                float(article.get(axis, nested.get(axis, 0.0)))
                for axis in AXIS_NAMES
            ],
            dtype=torch.float32,
        )

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "is_political": torch.tensor(article["is_political"], dtype=torch.long),
            "labels": labels,
            "article_idx": torch.tensor(chunk["article_idx"], dtype=torch.long),
        }

    # ------------------------------------------------------------------
    # Helpers para DataModule
    # ------------------------------------------------------------------
    @property
    def n_articles(self) -> int:
        """Cantidad de artículos únicos (no de chunks)."""
        return len(self.articles)

    def chunk_indices_for_articles(self, article_indices: list[int]) -> list[int]:
        """Devuelve los índices de chunks que pertenecen a un conjunto de artículos.

        Se usa en DataModule para mapear splits a-nivel-artículo → chunks.
        """
        article_set = set(article_indices)
        return [
            i for i, chunk in enumerate(self.chunks)
            if chunk["article_idx"] in article_set
        ]
