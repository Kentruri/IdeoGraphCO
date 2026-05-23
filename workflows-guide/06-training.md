# 6 — Training

Fine-tuning de un encoder (default ConfliBERT) + 8 cabezas MLP independientes
con PyTorch Lightning + Hydra. Loss: MSE sobre los 8 ejes.

## Comando

```bash
python -m src.training.train
```

## Overrides Hydra

```bash
# Otro encoder
python -m src.training.train model=maria

# Hiperparámetros
python -m src.training.train model.learning_rate=1e-5 trainer.max_epochs=15

# Otra semilla
python -m src.training.train data.seed=43
```

## Configs

| Archivo | Qué configura |
|---------|---------------|
| `configs/model/{default,confliberto,maria,beto}.yaml` | Encoder, LR, dropout, warmup |
| `configs/data/default.yaml` | Path del JSONL, batch_size, max_length, splits |
| `configs/trainer/default.yaml` | Epochs, precision, early stopping |

## Output

| Archivo | Contenido |
|---------|-----------|
| `logs/checkpoints/<alias>/best.ckpt` | Mejor checkpoint según `val/loss` |
| `logs/benchmark/<alias>/metrics.json` | Métricas finales sobre test (gold) |
| `logs/lightning_logs/<alias>/` | TensorBoard |

## Componentes

- [src/training/train.py](../src/training/train.py) — entry Hydra
- [src/training/models/ideovect_model.py](../src/training/models/ideovect_model.py) — IdeoVectModel
- [src/training/data/datamodule.py](../src/training/data/datamodule.py) — Lightning DataModule
