# IdeoGraphCO

Sistema de regresión multisalida para cuantificar intensidad ideológica en
noticias colombianas en 8 dimensiones simultáneas. Salida: vector en `[0,1]⁸`
representable como radar chart.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # añadir GEMINI_API_KEY
```

## Uso rápido

```bash
# 1. Scrape + clean + filter (un solo comando)
python scripts/scraper.py

# 2. Labeling silver con LLM
python scripts/label.py --input data/raw/articles.jsonl

# 3. Splits + training
python scripts/prepare_splits.py
python -m src.training.train
```

Pipeline completo en [PIPELINE.md](PIPELINE.md). Detalle por etapa en
[workflows-guide/](workflows-guide/).

## Estructura

```
src/
├── core/          # ids, paths, schema (AXIS_NAMES único)
├── scraper/       # scraping + cleaning + filter LLM
├── agents/silver/ # LLM-as-a-Judge
├── training/      # data, models, train, benchmark
└── inference/     # predict + radar charts
```

## Stack

- PyTorch Lightning + Hydra
- ConfliBERT-Spanish (encoder)
- Trafilatura (scraping)
- Gemini API (silver labels, filter)
- DVC (versionado de datos)
