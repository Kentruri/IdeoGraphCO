"""Predictor — carga un checkpoint y genera el vector ideológico de 8 dims."""

from pathlib import Path

import torch
from transformers import AutoTokenizer

from src.core.schema import AXIS_NAMES
from src.training.models.ideovect_model import IdeoVectModel


class IdeoVectPredictor:
    """Recibe texto plano → devuelve dict con scores ideológicos (0-100)."""

    def __init__(
        self,
        checkpoint_path: str | Path,
        device: str | None = None,
    ) -> None:
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = torch.device(device)

        # Cargar modelo desde checkpoint de Lightning
        self.model = IdeoVectModel.load_from_checkpoint(
            str(checkpoint_path), map_location=self.device,
        )
        self.model.eval()
        self.model.to(self.device)

        # Tokenizer del mismo encoder
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model.hparams.model_name,
        )

    @torch.no_grad()
    def predict(self, text: str) -> dict:
        """Predice los scores ideológicos de un texto.

        El modelo asume que el texto es político (responsabilidad del caller
        validar eso aguas arriba si es necesario).

        Returns:
            {
                "axes": {
                    "personalismo": 72.1,
                    "institucionalismo": 15.3,
                    ...
                }
            }
        """
        encoding = self.tokenizer(
            text,
            max_length=512,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        input_ids = encoding["input_ids"].to(self.device)
        attention_mask = encoding["attention_mask"].to(self.device)

        axis_scores = self.model(input_ids, attention_mask)

        # Scores de ejes (escalar de [0,1] a [0,100])
        scores = axis_scores.squeeze(0).cpu().tolist()
        axes = {
            name: round(score * 100, 2)
            for name, score in zip(AXIS_NAMES, scores)
        }

        return {"axes": axes}

    def predict_batch(self, texts: list[str]) -> list[dict]:
        """Predice scores para múltiples textos."""
        return [self.predict(text) for text in texts]
