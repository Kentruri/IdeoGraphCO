"""LightningDataModule article-level para el clasificador multiclase.

Cada item del dataset es un artículo entero (con K chunks). El collate_fn
apila artículos en un batch (B, K_max, L) y hace padding de chunks.

Soporta dos modos de splits:
1. **Splits desde disco** (`splits_path=<archivo>`): pre-computados a nivel
   ARTÍCULO. Se usan directamente como índices del Dataset.
2. **Random split en runtime**: divide aleatoriamente con semilla determinista.
"""

from __future__ import annotations

import json
import random
from functools import partial
from pathlib import Path

import pytorch_lightning as L
import numpy as np
import torch
from torch.utils.data import DataLoader, Subset, random_split

from src.training.data.dataset import IdeoGraphDataset, collate_articles


def _seed_worker(worker_id: int) -> None:
    """Siembra deterministicamente cada worker de PyTorch."""
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


class IdeoGraphDataModule(L.LightningDataModule):
    """Orquesta carga, splits y DataLoaders (article-level)."""

    def __init__(
        self,
        data_path: str | Path,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        batch_size: int = 16,
        num_workers: int = 4,
        pin_memory: bool = True,
        val_split: float = 0.15,
        test_split: float = 0.15,
        seed: int = 42,
        splits_path: str | Path | None = None,
        # Chunking (article-level)
        chunk_size: int = 512,
        chunk_stride: int = 384,
        max_chunks: int = 8,
        chunking_strategy: str = "sliding_window",
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        self.data_path = Path(data_path)
        self.model_name = model_name
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.pin_memory = pin_memory
        self.val_split = val_split
        self.test_split = test_split
        self.seed = seed
        self.splits_path = Path(splits_path) if splits_path else None

        self.chunk_size = chunk_size
        self.chunk_stride = chunk_stride
        self.max_chunks = max_chunks
        self.chunking_strategy = chunking_strategy

        self.train_ds: torch.utils.data.Dataset | None = None
        self.val_ds: torch.utils.data.Dataset | None = None
        self.test_ds: torch.utils.data.Dataset | None = None

    def setup(self, stage: str | None = None) -> None:
        """Carga el dataset completo y lo divide en train/val/test."""
        full_dataset = IdeoGraphDataset(
            data_path=self.data_path,
            model_name=self.model_name,
            chunk_size=self.chunk_size,
            chunk_stride=self.chunk_stride,
            max_chunks=self.max_chunks,
            chunking_strategy=self.chunking_strategy,
        )

        if self.splits_path and self.splits_path.exists():
            with open(self.splits_path, encoding="utf-8") as f:
                splits = json.load(f)

            self.train_ds = Subset(full_dataset, splits["train"])
            self.val_ds = Subset(full_dataset, splits["val"])
            self.test_ds = Subset(full_dataset, splits["test"])
        else:
            total = len(full_dataset)
            test_size = int(total * self.test_split)
            val_size = int(total * self.val_split)
            train_size = total - val_size - test_size

            generator = torch.Generator().manual_seed(self.seed)
            self.train_ds, self.val_ds, self.test_ds = random_split(
                full_dataset,
                [train_size, val_size, test_size],
                generator=generator,
            )

    def _build_generator(self) -> torch.Generator:
        g = torch.Generator()
        g.manual_seed(self.seed)
        return g

    def _collate(self):
        return partial(collate_articles, pad_chunk_len=self.chunk_size)

    def train_dataloader(self) -> DataLoader:
        return DataLoader(
            self.train_ds,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            worker_init_fn=_seed_worker,
            generator=self._build_generator(),
            persistent_workers=self.num_workers > 0,
            collate_fn=self._collate(),
        )

    def val_dataloader(self) -> DataLoader:
        return DataLoader(
            self.val_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            worker_init_fn=_seed_worker,
            persistent_workers=self.num_workers > 0,
            collate_fn=self._collate(),
        )

    def test_dataloader(self) -> DataLoader:
        return DataLoader(
            self.test_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
            worker_init_fn=_seed_worker,
            persistent_workers=self.num_workers > 0,
            collate_fn=self._collate(),
        )
