# IdeoGraphCO

Clasificador multiclase probabilístico de ideología política en noticias
colombianas. Cada artículo se asigna a **1 de 8 clases** (single-label);
la salida es una distribución de probabilidades sobre las 8 ideologías,
visualizable como mapa de calor.

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

# 4. Benchmark de los 4 encoders del anteproyecto
python scripts/benchmark.py --seeds 42 43 44
python scripts/compare_models.py
```

Pipeline completo en [PIPELINE.md](PIPELINE.md). Detalle por etapa en
[workflows-guide/](workflows-guide/). Decisiones pendientes con el director
en [docs/preguntas-director.md](docs/preguntas-director.md).

## Estructura

```
src/
├── core/          # ids, paths, schema (IDEOLOGY_CLASSES único)
├── scraper/       # scraping + cleaning + filter LLM
├── agents/silver/ # LLM-as-a-Judge
├── training/      # data, models, train, benchmark
└── inference/     # predictor + heatmap
```

## Stack

- PyTorch Lightning + Hydra
- 4 encoders del OE2: BETO / ConfliBERT-Spanish / XLM-RoBERTa / XLNet (TBD)
- Trafilatura (scraping)
- Gemini API (silver labels, filter)
- torchmetrics (F1 Macro, Confusion Matrix, ...)
- Plotly (heatmap)
- DVC (versionado de datos)
