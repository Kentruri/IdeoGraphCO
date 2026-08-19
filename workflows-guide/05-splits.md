# 5 — Dataset canónico + splits (train / val / test)

Construye `data/processed/dataset.jsonl` (silver + gold humano fusionado) y
pre-computa los splits **por ID** a disco, para que TODAS las corridas del
benchmark usen exactamente los mismos artículos.

Garantías (v2):

- **test = gold con etiquetas HUMANAS** (`gold_set_v2_labeled.jsonl`, salida
  de `ingest_gold.py`). Sin ese archivo el script se niega: evaluar contra
  etiquetas del mismo LLM que etiquetó el train es circular e invalida OE3.
- **Splits por ID** (no por índice): si el JSONL crece o se reordena, nada
  se corre de puesto.
- **Estratificación por clase** en train/val.
- **Anti-fuga**: near-duplicados del test (mismo hash de contenido o mismo
  título normalizado — cables republicados) se excluyen de train/val.

## Comando

```bash
python scripts/prepare_splits.py --gold-labeled annotation/gold_set_v2_labeled.jsonl
```

## Flags útiles

- `--val-ratio 0.15` — fracción de los no-gold que va a val (default 0.15)
- `--seed 42` — semilla del shuffle
- `--input PATH` — JSONL silver alternativo
- `--allow-silver-test` — **SOLO desarrollo**: permite test con etiquetas
  silver (imprime advertencia; las métricas NO sirven para la tesis)

## Output

`data/processed/dataset.jsonl` + `data/processed/splits.json`:

```json
{
  "version": 2,
  "id_based": true,
  "dataset_file": "data/processed/dataset.jsonl",
  "test_label_source": "human",
  "stratified": true,
  "leaked_excluded": 3,
  "train": ["a1b2c3...", ...],
  "val":   ["d4e5f6...", ...],
  "test":  ["<IDs del gold humano>"]
}
```

El resumen imprime la distribución de clases por split — si una clase queda
sin ejemplos de train, lo verás ahí (accionable con
`scripts/analyze_class_balance.py`).

## Cuándo regenerar

- Después de re-etiquetar el silver o de un scrape nuevo
- Después de una nueva ingesta del gold (`ingest_gold.py`)

## Componente

- [scripts/prepare_splits.py](../scripts/prepare_splits.py)
