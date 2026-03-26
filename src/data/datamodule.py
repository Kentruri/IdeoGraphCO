"""LightningDataModule para el pipeline de datos de IdeoGraphCO."""

from pathlib import Path

import lightning as L
from torch.utils.data import DataLoader, random_split

from src.data.dataset import IdeoGraphDataset


class IdeoGraphDataModule(L.LightningDataModule):
    """Orquesta carga, splits y DataLoaders.

    Espera un archivo JSONL en `data_path` con el formato definido
    en IdeoGraphDataset.
    """

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

        self.train_ds: IdeoGraphDataset | None = None
        self.val_ds: IdeoGraphDataset | None = None
        self.test_ds: IdeoGraphDataset | None = None

    def setup(self, stage: str | None = None) -> None:
        """Carga el dataset completo y lo divide en train/val/test."""
        full_dataset = IdeoGraphDataset(
            data_path=self.data_path,
            model_name=self.model_name,
            max_length=self.max_length,
        )

        total = len(full_dataset)
        test_size = int(total * self.test_split)
        val_size = int(total * self.val_split)
        train_size = total - val_size - test_size

        self.train_ds, self.val_ds, self.test_ds = random_split(
            full_dataset,
            [train_size, val_size, test_size],
            generator=__import__("torch").Generator().manual_seed(self.seed),
        )

    def train_dataloader(self) -> DataLoader:
        return DataLoader(
            self.train_ds,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
        )

    def val_dataloader(self) -> DataLoader:
        return DataLoader(
            self.val_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
        )

    def test_dataloader(self) -> DataLoader:
        return DataLoader(
            self.test_ds,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=self.pin_memory,
        )
