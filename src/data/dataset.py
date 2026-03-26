"""Dataset para noticias colombianas con etiquetas ideológicas de 8 ejes."""

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer

from src.models.ideovect_model import AXIS_NAMES


class IdeoGraphDataset(Dataset):
    """Carga noticias etiquetadas y las tokeniza para ConfliBERT.

    Formato esperado en data/interim/ (un JSON por línea — JSONL):
        {
            "text": "El presidente anunció...",
            "is_political": 1,
            "labels": {
                "personalismo": 0.72,
                "institucionalismo": 0.15,
                ...
            }
        }

    Los scores en labels deben estar normalizados a [0, 1].
    """

    def __init__(
        self,
        data_path: Path,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        max_length: int = 512,
    ) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.max_length = max_length
        self.samples = self._load(data_path)

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

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        sample = self.samples[idx]

        # Tokenización
        encoding = self.tokenizer(
            sample["text"],
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        # Etiquetas de los 8 ejes (en orden canónico)
        label_dict = sample.get("labels", {})
        labels = torch.tensor(
            [label_dict.get(axis, 0.0) for axis in AXIS_NAMES],
            dtype=torch.float32,
        )

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "is_political": torch.tensor(sample["is_political"], dtype=torch.long),
            "labels": labels,
        }
