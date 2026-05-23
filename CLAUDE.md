# CLAUDE.md — IdeoGraphCO

## Proyecto

Sistema de **regresión multisalida** que cuantifica intensidad ideológica en
noticias colombianas en 8 dimensiones simultáneas. Trabajo de grado universitario.

En lugar de clasificar izquierda/derecha, genera una "huella digital
ideológica" como vector en `[0, 1]⁸` representable en radar chart.

## Los 8 ejes (4 pares opuestos)

| Eje | Opuesto |
|-----|---------|
| Personalismo | Institucionalismo |
| Populismo | Doctrinarismo |
| Soberanismo | Globalismo |
| Conservadurismo | Progresismo |

Definiciones, marcadores y ejemplos en
[src/agents/silver/codebook.py](src/agents/silver/codebook.py).

## Arquitectura del modelo

```
texto → ConfliBERT → [CLS] → 8 × MLP independientes (Sigmoid) → vector [0,1]⁸
```

- **Encoder**: ConfliBERT-Spanish (`eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1`)
- **Cabezas**: 8 MLPs independientes (`Linear→ReLU→Dropout→Linear→Sigmoid`)
- **Loss**: `MSE(pred, target)` sobre los 8 ejes
- **Métricas**: MSE y R² por eje (`torchmetrics`)
- **Sin cabeza de politicidad**: el dataset es 100% político por construcción
  (filtrado aguas arriba por el LLM filter del scraper)

## Escalas y dataset

- **JSONL etiquetado** (`data/interim/labeled_news.jsonl`): 8 floats en `[0, 1]`.
  Sin campo `is_political`.
- **Silver (LLM)**: scores continuos. El LLM da `0.42`, `0.07`, `0.83`, etc.
  Los 5 niveles del codebook (Ausente / Leve / Moderado / Marcado / Dominante)
  son solo referencias semánticas, no anclajes obligatorios.
- **Gold (humano)**: enteros 1-5 en el Excel. Mapeo:
  `1→0.00, 2→0.25, 3→0.50, 4→0.75, 5→1.00`.

## Pipeline de datos

```
scraper.py (scrape+clean+filter LLM) → data/raw/articles.jsonl
        ↓
label.py (LLM-as-a-Judge, escala continua) → data/interim/labeled_news.jsonl
        ↓
prepare_gold_set.py (muestreo + Excel) → anotación humana
        ↓
prepare_splits.py (test=gold, train/val=resto) → data/processed/splits.json
        ↓
src.training.train → checkpoints
        ↓
src.inference.predict → radar HTML
```

## Estructura del proyecto (monorepo)

```
src/
├── core/                  # ids, paths, AXIS_NAMES (fuente única)
├── scraper/
│   ├── sources.py         # 83 fuentes en 7 categorías
│   ├── parser.py          # trafilatura + UA rotativo
│   ├── cleaner.py         # regex (cookies, CTAs, URLs, handles)
│   ├── article_filter.py  # LLM filter con escalado automático
│   ├── prompts.py         # FILTER_SYSTEM_PROMPT aislado
│   ├── pipeline.py        # orquesta scrape→clean→filter
│   ├── db.py              # SQLite (dedup persistente)
│   └── robots.py
├── agents/
│   ├── silver/            # LLM-as-a-Judge (judge.py, codebook.py)
│   └── gold/              # (tooling de anotación humana)
├── training/
│   ├── data/              # dataset + datamodule (Lightning)
│   ├── models/            # IdeoVectModel
│   ├── benchmark/         # registry de encoders
│   └── train.py           # Hydra + Lightning Trainer
└── inference/             # predictor + radar charts (Plotly)

scripts/                   # CLIs delgados (orquestan src/)
configs/                   # Hydra (model, data, trainer)
annotation/                # gold set v1 (xlsx + jsonl + ids.json)
data/                      # versionado con DVC
docs/                      # guías técnicas (data-versioning, etc.)
workflows-guide/           # guía paso a paso por etapa
```

## Fuentes (83 en 7 categorías)

`src/scraper/sources.py` — distribución actual:

| Categoría | # |
|-----------|---|
| Nacional | 15 |
| Independiente | 19 |
| Regional | 15 |
| Institucional | 10 |
| Judicial (★ nueva) | 6 |
| Opinion (think tanks) | 10 |
| Gremial | 8 |

## Stack técnico

- **PyTorch Lightning + Hydra** — entrenamiento y configuración
- **ConfliBERT-Spanish** — encoder pre-entrenado en conflicto/política
- **Trafilatura** — extracción robusta de artículos
- **Gemini API** — silver labels + filter LLM (con escalado auto)
- **torchmetrics** — MSE y R² por eje
- **Plotly** — radar charts interactivos
- **DVC** — versionado de `data/`

## Convenciones de código

- Python >= 3.10
- Linter: ruff
- Tests: pytest (en `tests/`)
- Idioma del código: inglés (clases, funciones, variables)
- Idioma de docs/comentarios: español donde aporta contexto político
