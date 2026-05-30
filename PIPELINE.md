# Pipeline IdeoGraphCO

Regresión multisalida: noticia → vector `[0,1]⁸` (8 ejes ideológicos) → radar chart.

## Etapas

| # | Etapa | Comando | Output |
|---|-------|---------|--------|
| 1 | Scrape + clean + filter LLM | `python scripts/scraper.py` | `data/raw/articles.jsonl` |
| 2 | Labeling silver (LLM, escala continua [0,1]) | `python scripts/label.py --input data/raw/articles.jsonl` | `data/silver/silver_set.jsonl` |
| 3 | Gold set (Excel para anotación humana) | `python scripts/prepare_gold_set.py` | `annotation/gold_set_v1.xlsx` |
| 4 | Splits (test=gold, train/val=resto) | `python scripts/prepare_splits.py` | `data/processed/splits.json` |
| 5 | Training de 1 modelo | `python -m src.training.train` | `logs/checkpoints/<alias>/best.ckpt` |
| 5b | Benchmark de N encoders × M semillas | `python scripts/benchmark.py --seeds 42 43 44` | `reports/benchmark_report.md` |
| 6 | Inferencia | `python -m src.inference.predict --text "..."` | radar HTML |

## Notas clave

- **No hay campo `is_political`** en el dataset: el filter LLM (etapa 1) ya descarta los no-políticos.
- **Escala continua**: el silver da floats en `[0, 1]` (ej. `0.42`). El gold humano usa enteros 1-5 que se mapean a `{0, 0.25, 0.5, 0.75, 1}`.
- **Escalado automático del filter**: si `gemini-2.5-flash-lite` da confidence < 0.7, re-llama a `gemini-2.5-flash`.

Más detalle por etapa: [workflows-guide/](workflows-guide/).
