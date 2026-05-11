"""LightningDataModule para el pipeline de datos de IdeoGraphCO.

Soporta dos modos de splits:
1. **Splits desde disco** (`splits_path=<archivo>`): pre-computados, garantiza
   que cualquier corrida futura use exactamente los mismos índices. Necesario
   para comparar modelos en un benchmark.
2. **Random split en runtime**: divide aleatoriamente con semilla determinista.
   Más simple para experimentos rápidos pero los índices cambian si se añaden
   muestras al JSONL.

Para el benchmark se recomienda el modo 1. Ver `scripts/prepare_splits.py`.
"""

import json
import random
from pathlib import Path

import lightning as L
import numpy as np
import torch
from torch.utils.data import DataLoader, Subset, random_split

from src.data.dataset import IdeoGraphDataset


def _seed_worker(worker_id: int) -> None:
    """Siembra deterministicamente cada worker de PyTorch.

    Sin esto, cada worker hace su propia siembra automática y el orden de
    batches puede variar entre corridas con la misma seed global.
    """
    worker_seed = torch.initial_seed() % 2**32
    np.random.seed(worker_seed)
    random.seed(worker_seed)


class IdeoGraphDataModule(L.LightningDataModule):
    """Orquesta carga, splits y DataLoaders."""

    def __init__(
        self,
        data_path: str | Path,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        max_length: int = 512,
        batch_size: int = 16,
        num_workers: int = 4,
        pin_memory: bool = True,
        val_split: float = 0.15,
        test_split: float = 0.15,
        seed: int = 42,
        splits_path: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.save_hyperparameters()

        self.data_path = Path(data_path)
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.pin_memory = pin_memory
        self.val_split = val_split
        self.test_split = test_split
        self.seed = seed
        self.splits_path = Path(splits_path) if splits_path else None

        self.train_ds: torch.utils.data.Dataset | None = None
        self.val_ds: torch.utils.data.Dataset | None = None
        self.test_ds: torch.utils.data.Dataset | None = None

    def setup(self, stage: str | None = None) -> None:
        """Carga el dataset completo y lo divide en train/val/test."""
        full_dataset = IdeoGraphDataset(
            data_path=self.data_path,
            model_name=self.model_name,
            max_length=self.max_length,
        )

        if self.splits_path and self.splits_path.exists():
            # Modo 1: splits pre-computados desde disco
            with open(self.splits_path, encoding="utf-8") as f:
                splits = json.load(f)
            self.train_ds = Subset(full_dataset, splits["train"])
            self.val_ds = Subset(full_dataset, splits["val"])
            self.test_ds = Subset(full_dataset, splits["test"])
        else:
            # Modo 2: random_split con seed determinista
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
        """Generator determinista para shuffling del DataLoader."""
        g = torch.Generator()
        g.manual_seed(self.seed)
        return g

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
        )
