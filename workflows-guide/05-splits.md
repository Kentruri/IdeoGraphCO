# 5 — Splits (train / val / test)

Pre-computa los splits a disco para que TODAS las corridas del benchmark
usen exactamente los mismos artículos. `test` = gold humano, `train+val` =
resto del corpus silver.

## Comando

```bash
python scripts/prepare_splits.py
```

## Flags útiles

- `--val-ratio 0.15` — fracción de los no-gold que va a val (default 0.15)
- `--seed 42` — semilla del shuffle
- `--gold-ids PATH` — JSON alternativo con IDs gold
- `--no-gold` — split tradicional sin gold (train/val/test al azar)

## Output

`data/processed/splits.json`:

```json
{
  "source_file": "data/silver/silver_set.jsonl",
  "total_samples": 1000,
  "gold_used": true,
  "train": [12, 47, 89, ...],
  "val":   [3, 18, ...],
  "test":  [<índices de los gold IDs>]
}
```

## Cuándo regenerar

- Después de cualquier cambio en `silver_set.jsonl` (re-etiquetado, scrape nuevo)
- Después de actualizar `gold_set_v1_ids.json`

## Componente

- [scripts/prepare_splits.py](../scripts/prepare_splits.py)
