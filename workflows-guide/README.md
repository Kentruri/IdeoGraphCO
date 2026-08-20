# Guías por etapa

Resumen del pipeline en [PIPELINE.md](../PIPELINE.md). Aquí, una página por etapa.

| # | Guía | Comando principal | Output |
|---|------|-------------------|--------|
| 1 | [Scraping](01-scraping.md) (scrape+clean+filter, `--workers/--gdelt/--prefilter`) | `python scripts/scraper.py` | `data/raw/articles.jsonl` |
| 2 | [Labeling silver](02-labeling.md) (LLM, **clase dominante** + scores) | `python scripts/label.py` | `data/silver/silver_set.jsonl` |
| 3 | [Sample review](03-sample-review.md) (opcional, validación calidad) | `python scripts/generate_sample.py` | `muestra_ideologica.xlsx` |
| 4 | [Gold set v2](04-gold-set.md) (doble anotación + **Krippendorff α** + consenso) | `python scripts/prepare_gold_set.py` → `python scripts/ingest_gold.py` | `annotation/gold_set_v2_labeled.jsonl` |
| 5 | [Splits](05-splits.md) (dataset canónico + splits por ID, test=gold humano) | `python scripts/prepare_splits.py --gold-labeled ...` | `data/processed/dataset.jsonl` + `splits.json` |
| 6 | [Training](06-training.md) (Hydra + Lightning) | `python -m src.training.train` | `logs/checkpoints/...` |
| 7 | [Benchmark](07-benchmark.md) (selección en VALIDACIÓN; test una vez con `final_eval.py`) | `python scripts/benchmark.py --seeds 42 43 44` | `reports/benchmark_report.md` + `reports/evaluacion_final.md` |
| 8 | [Inference](08-inference.md) (heatmap HTML + servicio `POST /classify`) | ver guía | heatmap HTML / API |
| 9 | [Compartir datos](09-compartir-datos.md) (DVC + Google Drive) | `dvc add data/raw` → `dvc push` | contenido en Drive, hashes en git |

## Versionado de datos

Las carpetas `data/raw/`, `data/silver/`, `data/processed/` se versionan con
DVC (no git): el contenido va a Google Drive y en git solo quedan los archivos
`.dvc` con los hashes. Setup y comandos en
[09-compartir-datos.md](09-compartir-datos.md); el detalle de cómo funciona,
en [docs/data-versioning.md](../docs/data-versioning.md).
