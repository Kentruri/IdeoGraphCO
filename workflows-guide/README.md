# Pipeline IdeoGraphCO — Guía completa

Sistema de regresión multisalida para cuantificar la intensidad ideológica
en noticias colombianas a través de 8 dimensiones simultáneas.

## Pipeline en orden

```
┌──────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────────┐
│ 1. SCRAPING  │→│ 2. CLEANING │→│ 3. LABELING     │→│ 4. FILTERING │
│              │  │  (regex)    │  │ LLM-as-a-Judge  │  │   (LLM)      │
└──────────────┘  └─────────────┘  └─────────────────┘  └──────────────┘
                                                                 │
                                                                 ▼
                                                    ┌──────────────────┐
                                                    │ 5. EXCEL DIRECTOR│
                                                    └──────────────────┘
                                                                 │
                                                                 ▼
                                                    ┌──────────────────┐
                                                    │  6. ENTRENAMIENTO│
                                                    └──────────────────┘
                                                                 │
                                                                 ▼
                                                    ┌──────────────────┐
                                                    │  7. INFERENCIA   │
                                                    └──────────────────┘

                          (opcional, para tesis)
                                                                 │
                                                                 ▼
                                                    ┌──────────────────┐
                                                    │  8. BENCHMARK    │
                                                    │  (3 encoders)    │
                                                    └──────────────────┘
```

## Setup inicial

```bash
# Crear entorno virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar todas las dependencias
pip install -r requirements.txt

# Configurar API key de Gemini
cp .env.example .env
# Editar .env y añadir GEMINI_API_KEY
```

Para obtener la API key gratis: https://aistudio.google.com → Get API Key

## Pasos del pipeline

| # | Paso | Tiempo | Costo | Salida |
|---|------|--------|-------|--------|
| 1 | [Scraping](01-scraping.md) | 2-4 horas | gratis | `data/raw/news.jsonl` |
| 2 | [Cleaning](02-cleaning.md) | segundos | gratis | `data/raw/news_clean.jsonl` |
| 3 | [Labeling](03-labeling.md) | ~30 min | ~COP 1,800 | `data/interim/labeled_news.jsonl` |
| 4 | [Filtering](04-filtering.md) | ~30 min | ~COP 250 | `data/interim/labeled_news_clean.jsonl` |
| 5 | [Excel director](05-sample-export.md) | segundos | gratis | `muestra_ideologica.xlsx` |
| 6 | [Entrenamiento](06-training.md) | 1-3 horas | gratis | `logs/checkpoints/best.ckpt` |
| 7 | [Inferencia](07-inference.md) | segundos | gratis | radar charts HTML |
| 8 | [Benchmark](08-benchmark.md) | 6-8 horas | gratis | `reports/benchmark_report.md` |

## Comandos rápidos

```bash
# Activar siempre el entorno virtual primero
source .venv/bin/activate

# 1. Scraping (~2-4 horas)
caffeinate -d -i -s &
python scripts/scraper.py --max-articles 100

# 2. Limpieza con regex (segundos)
python scripts/clean.py

# 3. Etiquetado con LLM (Gemini) — ~30 min
python scripts/label.py --model gemini-2.5-flash-lite

# 4. Filtrado de basura con LLM — ~30 min
python scripts/filter_articles.py --model gemini-2.5-flash-lite

# 5. Generar Excel para el director
python scripts/generate_sample.py

# 6. Entrenar el modelo
python -m src.training.train

# 7. Inferencia con un artículo nuevo
python -m src.inference.predict --text "..."

# 8. (Opcional) Benchmark entre 3 encoders
python scripts/benchmark.py
python scripts/compare_models.py
```

## Estructura de datos

```
data/
├── raw/
│   ├── news.jsonl              # Output de scraping
│   ├── news_clean.jsonl        # Output de cleaning (regex)
│   └── .clean_cursor           # Cursor del cleaner
├── interim/
│   ├── labeled_news.jsonl      # Output de labeling
│   ├── labeled_news_clean.jsonl # Output de filtering (LLM)
│   ├── .label_cursor           # Cursor del labeler
│   └── .filter_cursor          # Cursor del filter
└── processed/                  # (Para futuro: tensores de entrenamiento)

logs/
└── checkpoints/                # Modelos entrenados (.ckpt)
```

## Ejecuciones idempotentes

Todos los scripts usan **cursores** para no reprocesar trabajo previo:

- Si se interrumpe el scraping → vuelves a correr el comando y continúa
- Si se interrumpe el labeling → ídem
- Si se interrumpe el filtering → ídem

Para forzar reprocesar todo desde cero: agregar flag `--force` (o `--force` en los scripts que lo soporten).

## Documentación detallada

Lee cada guía individual para detalles:

- [01 — Scraping](01-scraping.md) — Trafilatura + sitemaps + RSS de 30+ medios colombianos
- [02 — Cleaning](02-cleaning.md) — Regex para CTAs, cookie banners, paywalls
- [03 — Labeling](03-labeling.md) — LLM-as-a-Judge con codebook político
- [04 — Filtering](04-filtering.md) — Descarte de basura con LLM
- [05 — Excel director](05-sample-export.md) — Muestra de 200 artículos por ideología
- [06 — Entrenamiento](06-training.md) — ConfliBERT + 8 cabezas con Lightning + Hydra
- [07 — Inferencia](07-inference.md) — Predicción + radar charts
- [08 — Benchmark](08-benchmark.md) — Comparar ConfliBERT vs MarIA vs BETO

## Stack técnico

- **PyTorch Lightning + Hydra** — entrenamiento y configuración
- **ConfliBERT-Spanish** — encoder pre-entrenado en política en español
- **Trafilatura** — extracción de artículos (mejor que Newspaper4k)
- **Gemini API** — LLM-as-a-Judge para etiquetado silver
- **torchmetrics** — MSE y R² independientes por eje
- **Plotly** — radar charts interactivos
