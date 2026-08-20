"""Dataset article-level para el clasificador multiclase de ideología.

Las etiquetas se validan EAGER al cargar (no lazy en __getitem__): un
artículo con etiqueta inválida aborta la carga con su `id` en el mensaje,
en vez de crashear a mitad de entrenamiento. Los empates de argmax en el
formato legacy se reportan con un warning agregado.

Cada item del dataset es UN ARTÍCULO completo con sus K chunks pre-tokenizados.
La agregación de chunks (V_doc = mean V_chunk_i) sucede en el modelo,
no aquí.

Formato de un ítem retornado por `__getitem__`:

    {
        "input_ids":       LongTensor  (K, L)    K chunks de L tokens
        "attention_mask":  LongTensor  (K, L)
        "chunk_mask":      LongTensor  (K,)      1 = chunk real (siempre 1
                                                 en este nivel; el padding a
                                                 K_max del batch lo hace el
                                                 collate_fn)
        "label":           LongTensor  scalar    índice de clase 0..7
        "article_idx":     LongTensor  scalar    índice global del artículo
    }

Estrategias de chunking:

- **truncate**: 1 chunk = primeros L tokens del artículo (baseline rápido).
- **sliding_window**: K chunks con overlap; K se capa a `max_chunks`.

Formato aceptado en el JSONL de labels:

- **Nuevo (categórico, TBD post-decisión del director)**:
      {"label": "populismo"}  o  {"label_idx": 2}
- **Legacy (silver continuo actual)**:
      {"personalismo": 0.42, "populismo": 0.83, ...}
  → se resuelve con argmax al vuelo (ver docs/preguntas-director.md tema 5).
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer

from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES, NUM_CLASSES
from src.core.text import build_model_input


def resolve_label_idx(article: dict) -> int:
    """Devuelve el índice de clase 0..7 leyendo el artículo en cualquier formato.

    Prioridad:
    1. `label_idx` (entero, formato nativo del clasificador).
    2. `label` (string, mapea con CLASS_TO_IDX).
    3. 8 scores continuos → argmax (legacy silver).
    """
    if "label_idx" in article:
        idx = int(article["label_idx"])
        if not 0 <= idx < NUM_CLASSES:
            raise ValueError(
                f"label_idx fuera de rango: {idx} (esperado 0..{NUM_CLASSES - 1})"
            )
        return idx

    label = article.get("label")
    if isinstance(label, str):
        if label not in CLASS_TO_IDX:
            raise ValueError(
                f"label desconocido: {label!r}. Válidos: {list(CLASS_TO_IDX)}"
            )
        return CLASS_TO_IDX[label]

    nested = article.get("labels", {})
    scores = [
        float(article.get(cls, nested.get(cls, 0.0)))
        for cls in IDEOLOGY_CLASSES
    ]
    if all(s == 0.0 for s in scores):
        raise ValueError(
            f"Artículo sin etiquetas ideológicas resolubles: keys={list(article)[:8]}"
        )
    return max(range(NUM_CLASSES), key=lambda i: scores[i])


def legacy_argmax_is_tie(article: dict) -> bool:
    """True si el artículo legacy (8 floats) tiene empate en el argmax.

    Con etiqueta explícita (`label`/`label_idx`) nunca hay empate.
    """
    if "label_idx" in article or isinstance(article.get("label"), str):
        return False
    nested = article.get("labels", {})
    scores = [
        float(article.get(cls, nested.get(cls, 0.0)))
        for cls in IDEOLOGY_CLASSES
    ]
    top = max(scores)
    return scores.count(top) > 1


class IdeoGraphDataset(Dataset):
    """Dataset article-level para el clasificador."""

    def __init__(
        self,
        data_path: Path,
        model_name: str = "eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1",
        chunk_size: int = 512,
        chunk_stride: int = 384,
        max_chunks: int = 8,
        chunking_strategy: str = "sliding_window",  # "truncate" | "sliding_window"
    ) -> None:
        if chunking_strategy not in ("truncate", "sliding_window"):
            raise ValueError(
                f"chunking_strategy desconocida: {chunking_strategy!r}."
            )
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.chunk_size = chunk_size
        self.chunk_stride = chunk_stride
        self.max_chunks = max_chunks
        self.chunking_strategy = chunking_strategy

        self._cls_id = self.tokenizer.cls_token_id
        self._sep_id = self.tokenizer.sep_token_id
        self._pad_id = self.tokenizer.pad_token_id
        # XLNet coloca <cls> al FINAL de la secuencia (formato canónico de su
        # pre-entrenamiento: contenido <sep> <cls>); la familia BERT lo lleva
        # al inicio. El modelo hace la misma detección vía config.model_type
        # para extraer el embedding de la posición correcta.
        self._cls_at_end = "xlnet" in type(self.tokenizer).__name__.lower()

        self.articles: list[dict] = self._load(data_path)
        # El troceo corre sobre la MISMA composición que ve el juez y la
        # inferencia (titular limpio + cuerpo): ver src/core/text.py.
        self._chunks_per_article: list[list[list[int]]] = [
            self._chunk_article(build_model_input(a.get("title"), a["text"]))
            for a in self.articles
        ]

    @staticmethod
    def _load(path: Path) -> list[dict]:
        import logging

        logger = logging.getLogger(__name__)
        samples: list[dict] = []
        ties = 0
        with open(path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                article = json.loads(line)
                # Validación eager: falla al CARGAR (con contexto), no a
                # mitad de entrenamiento.
                try:
                    resolve_label_idx(article)
                except ValueError as e:
                    raise ValueError(
                        f"{path}:{line_num} (id={article.get('id', '?')}): {e}"
                    ) from e
                if legacy_argmax_is_tie(article):
                    ties += 1
                samples.append(article)
        if ties:
            logger.warning(
                "%d/%d artículos legacy con EMPATE en el argmax (la clase se "
                "resuelve por orden de índice — sesgo sistemático). "
                "Re-etiquetar categórico con scripts/label.py --force lo elimina.",
                ties, len(samples),
            )
        return samples

    def _chunk_article(self, text: str) -> list[list[int]]:
        """Devuelve lista de listas de token IDs (sin CLS/SEP; se añaden luego)."""
        content_length = self.chunk_size - 2  # espacio para [CLS] y [SEP]
        full_ids: list[int] = self.tokenizer(
            text, add_special_tokens=False, truncation=False,
        )["input_ids"]

        if not full_ids:
            return [[]]

        if self.chunking_strategy == "truncate":
            return [full_ids[:content_length]]

        chunks: list[list[int]] = []
        start = 0
        while start < len(full_ids) and len(chunks) < self.max_chunks:
            end = min(start + content_length, len(full_ids))
            chunks.append(full_ids[start:end])
            if end == len(full_ids):
                break
            start += self.chunk_stride
        return chunks

    def __len__(self) -> int:
        return len(self.articles)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        article = self.articles[idx]
        chunks = self._chunks_per_article[idx]

        input_ids_list: list[list[int]] = []
        attention_mask_list: list[list[int]] = []
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
            attention_mask_list.append(mask)

        input_ids = torch.tensor(input_ids_list, dtype=torch.long)
        attention_mask = torch.tensor(attention_mask_list, dtype=torch.long)
        chunk_mask = torch.ones(len(chunks), dtype=torch.long)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "chunk_mask": chunk_mask,
            "label": torch.tensor(resolve_label_idx(article), dtype=torch.long),
            "article_idx": torch.tensor(idx, dtype=torch.long),
        }

    @property
    def n_articles(self) -> int:
        return len(self.articles)


def collate_articles(batch: list[dict], pad_chunk_len: int) -> dict[str, torch.Tensor]:
    """Apila artículos de longitud variable de chunks a un batch uniforme.

    Argumentos:
        batch: lista de items de IdeoGraphDataset.__getitem__.
        pad_chunk_len: longitud L de cada chunk (Dataset.chunk_size).

    Retorna:
        {
            "input_ids":      (B, K_max, L)
            "attention_mask": (B, K_max, L)
            "chunk_mask":     (B, K_max)
            "labels":         (B,)
            "article_idx":    (B,)
        }
    """
    B = len(batch)
    K_max = max(item["chunk_mask"].shape[0] for item in batch)
    L = pad_chunk_len

    input_ids = torch.zeros((B, K_max, L), dtype=torch.long)
    attention_mask = torch.zeros((B, K_max, L), dtype=torch.long)
    chunk_mask = torch.zeros((B, K_max), dtype=torch.long)
    labels = torch.empty(B, dtype=torch.long)
    article_idx = torch.empty(B, dtype=torch.long)

    for i, item in enumerate(batch):
        k = item["chunk_mask"].shape[0]
        input_ids[i, :k, :] = item["input_ids"]
        attention_mask[i, :k, :] = item["attention_mask"]
        chunk_mask[i, :k] = item["chunk_mask"]
        labels[i] = item["label"]
        article_idx[i] = item["article_idx"]

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "chunk_mask": chunk_mask,
        "labels": labels,
        "article_idx": article_idx,
    }
