# 6 — Training

Fine-tuning de un encoder (default ConfliBERT) + cabeza lineal 8-way con
softmax. Loss: Categorical Cross-Entropy. Métrica principal: F1 Macro.
Cada artículo se procesa como K chunks de 512 tokens; el modelo promedia
los K embeddings [CLS] antes de la cabeza (`V_doc = mean V_chunk_i`).

## Comando

```bash
python -m src.training.train
```

## Overrides Hydra

```bash
# Otro encoder del benchmark
python -m src.training.train model=beto
python -m src.training.train model=xlm-roberta
python -m src.training.train model=xlnet        # XLNet original (inglés, decisión ago-2026)

# Hiperparámetros
python -m src.training.train model.learning_rate=1e-5 trainer.max_epochs=15

# Chunking
python -m src.training.train data.chunk_size=384 data.max_chunks=4

# Otra semilla
python -m src.training.train data.seed=43

# Smoke test (1 batch de train/val/test)
python -m src.training.train trainer.fast_dev_run=true
```

## Configs

| Archivo | Qué configura |
|---------|---------------|
| `configs/model/{default,confliberto,beto,xlm-roberta,xlnet}.yaml` | Encoder, LR, dropout, warmup, `use_politicity_head` |
| `configs/data/default.yaml` | Path del JSONL, batch_size, chunk_size/stride/max_chunks, splits |
| `configs/trainer/default.yaml` | Epochs, precision, early stopping sobre F1 Macro |

## Output

| Archivo | Contenido |
|---------|-----------|
| `logs/checkpoints/<alias>/best.ckpt` | Mejor checkpoint según `val/f1_macro` |
| `logs/benchmark/<alias>/metrics.json` | Métricas finales sobre test + matriz de confusión |
| `logs/lightning_logs/<alias>/` | TensorBoard |

## Componentes

- [src/training/train.py](../src/training/train.py) — entry Hydra
- [src/training/models/ideoclassifier.py](../src/training/models/ideoclassifier.py) — IdeoClassifier
- [src/training/data/dataset.py](../src/training/data/dataset.py) — Dataset article-level + `collate_articles`
- [src/training/data/datamodule.py](../src/training/data/datamodule.py) — Lightning DataModule
