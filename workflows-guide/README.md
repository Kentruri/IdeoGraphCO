# Guías por etapa

Resumen del pipeline en [PIPELINE.md](../PIPELINE.md). Aquí, una página por etapa.

| # | Guía | Comando principal | Output |
|---|------|-------------------|--------|
| 1 | [Scraping](01-scraping.md) (scrape+clean+filter unificado) | `python scripts/scraper.py` | `data/raw/articles.jsonl` |
| 2 | [Labeling silver](02-labeling.md) (LLM, escala continua) | `python scripts/label.py` | `data/interim/labeled_news.jsonl` |
| 3 | [Sample review](03-sample-review.md) (opcional, validación calidad) | `python scripts/generate_sample.py` | `muestra_ideologica.xlsx` |
| 4 | [Gold set](04-gold-set.md) (anotación humana) | `python scripts/prepare_gold_set.py` | `annotation/gold_set_v1.xlsx` |
| 5 | [Splits](05-splits.md) (train/val/test, test=gold) | `python scripts/prepare_splits.py` | `data/processed/splits.json` |
| 6 | [Training](06-training.md) (Hydra + Lightning) | `python -m src.training.train` | `logs/checkpoints/...` |
| 7 | [Benchmark](07-benchmark.md) (N encoders × M semillas) | `python scripts/benchmark.py --seeds 42 43 44` | `reports/benchmark_report.md` |
| 8 | [Inference](08-inference.md) (radar HTML) | `python -m src.inference.predict --text "..."` | radar HTML |

## Versionado de datos

Las carpetas `data/raw/`, `data/interim/`, `data/processed/` se versionan con
DVC (no git). Ver [docs/data-versioning.md](../docs/data-versioning.md).
