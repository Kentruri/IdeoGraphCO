# IdeoGraphCO

Sistema de regresión multisalida basado en Transformers para la cuantificación volumétrica y multidimensional de ideologías políticas en el discurso mediático colombiano.

## Setup

```bash
# 1. Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
# Editar .env y añadir tu GEMINI_API_KEY
```

## Pipeline

```bash
# 1. Scrapear noticias políticas colombianas
python scripts/scraper.py --max-articles 100

# 2. Limpiar el texto
python scripts/clean.py

# 3. Etiquetar con LLM-as-a-Judge (Gemini)
python scripts/label.py
```

## Estructura

- `src/data/scraping/` — Scraper con trafilatura, sitemaps y RSS
- `src/labeling/` — Pipeline LLM-as-a-Judge (codebook + Gemini)
- `src/models/` — IdeoVectModel (ConfliBERT + 8 cabezas de regresión)
- `src/training/` — Entrenamiento con Lightning + Hydra
- `src/inference/` — Predicción + radar charts
- `configs/` — Configuración Hydra (model, data, trainer)
- `scripts/` — CLIs (scraper, clean, label)

## Stack técnico

- PyTorch Lightning + Hydra
- ConfliBERT-Spanish (encoder pre-entrenado)
- Trafilatura (extracción de artículos)
- Gemini API (LLM-as-a-Judge para etiquetado silver)
