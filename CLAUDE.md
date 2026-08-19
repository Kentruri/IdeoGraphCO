# CLAUDE.md — IdeoGraphCO

## Proyecto

**Clasificador multiclase probabilístico** de ideología política en noticias
colombianas. Trabajo de grado universitario.

Cada artículo se asigna a **una** de 8 clases ideológicas (single-label,
mutuamente excluyentes). El modelo devuelve una distribución de probabilidades
sobre las 8 clases; la salida se visualiza como **mapa de calor** (no radar).

> Diseño previo: era regresión multisalida sobre 8 ejes en `[0,1]⁸`. Se
> migró a clasificador multiclase por requisito del anteproyecto aprobado.
> Ver `docs/preguntas-director.md` para decisiones pendientes con el
> director (cabeza binaria de politicidad, XLNet en español, formato del
> silver, etc.).

## Las 8 clases ideológicas (4 pares opuestos)

| Clase | Opuesto |
|-------|---------|
| Populismo | Institucionalismo |
| Personalismo | Doctrinarismo |
| Soberanismo | Globalismo |
| Conservadurismo | Progresismo |

Definiciones y marcadores en
[src/agents/silver/codebook.py](src/agents/silver/codebook.py). Los pares
opuestos están declarados en `src.core.schema.OPPOSITE_PAIRS` y se usan
en el análisis de errores del OE3.

## Arquitectura del modelo

```
texto largo → K chunks de 512 tokens (sliding_window, stride=384)
                    ↓
              Encoder (BETO / ConfliBERT / XLM-RoBERTa / XLNet)
                    ↓
              K embeddings [CLS] — uno por chunk
                    ↓
              V_doc = (1/K) · Σ V_chunk_i    (agregación mean-pool con máscara)
                    ↓
              Dropout → Linear(H, 8) → Softmax (implícito en CE loss)
                    ↓
              P(clase | doc) sobre 8 ideologías
```

- **Loss**: Categorical Cross-Entropy.
- **Métricas** (`torchmetrics`, macro): Precision, Recall, F1, Accuracy,
  Confusion Matrix. `f1_macro` es la métrica principal del OE3.
- **Encoders del benchmark** (OE2):
  `dccuchile/bert-base-spanish-wwm-cased` (BETO),
  `eventdata-utd/ConfliBERT-Spanish-Beto-Cased-v1` (ConfliBERT),
  `FacebookAI/xlm-roberta-base` (XLM-RoBERTa),
  `microsoft/mdeberta-v3-base` (placeholder de XLNet — TBD).
- **Cabeza binaria de politicidad**: deshabilitada por defecto. Ver TBD en el
  docstring de `src/training/models/ideoclassifier.py` y
  `docs/preguntas-director.md` tema 1.

## Escalas y dataset

- **Formato categórico (actual, metodología del anteproyecto)**: el judge
  asigna la clase DOMINANTE → `{"label": "populismo", "label_idx": 2,
  "label_source": "silver-llm"}` + los 8 scores de intensidad en `[0,1]`
  como señal secundaria.
- **Formato legacy (silver continuo)** — solo 8 floats por artículo. El
  dataset lo convierte con `argmax` al vuelo vía `resolve_label_idx()`
  (con warning por empates). Deprecado: re-etiquetar con
  `python scripts/label.py --force`.
- **Gold (humano) v2**: enteros 1-5 por eje + `clase_dominante` obligatoria
  en el Excel. Doble anotación independiente con solape → Krippendorff
  α ≥ 0.8 (`scripts/ingest_gold.py` + `src/agents/gold/agreement.py`);
  discrepancias por consenso. Salida con `label_source: human*`.

## Pipeline de datos

```
scraper.py (scrape+clean+filter LLM) → data/raw/articles.jsonl
        ↓
label.py (judge categórico: dominante + scores) → data/silver/silver_set.jsonl
        ↓
prepare_gold_set.py (libros por anotador + solape) → anotación humana
        ↓
ingest_gold.py (α de Krippendorff + consenso) → annotation/gold_set_v2_labeled.jsonl
        ↓
prepare_splits.py (dataset canónico + splits por ID, test=gold HUMANO)
        → data/processed/dataset.jsonl + splits.json
        ↓
src.training.train / scripts/benchmark.py (selección en VALIDACIÓN)
        ↓
scripts/final_eval.py (test UNA vez, P3.1) → reports/evaluacion_final.md
        ↓
src.inference.predictor (heatmap) · src.inference.api (POST /classify para el BE)
```

## Estructura del proyecto (monorepo)

```
src/
├── core/                  # ids, paths, IDEOLOGY_CLASSES (fuente única)
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
│   ├── data/              # dataset (article-level) + datamodule + collate
│   ├── models/            # IdeoClassifier
│   ├── benchmark/         # registry de los 4 encoders del PDF
│   └── train.py           # Hydra + Lightning Trainer
└── inference/             # predictor + heatmap (Plotly)

scripts/                   # CLIs delgados (orquestan src/)
configs/                   # Hydra (model, data, trainer)
annotation/                # gold set v1 (xlsx + jsonl + ids.json)
data/                      # versionado con DVC
docs/                      # guías técnicas + preguntas al director
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
| Judicial | 6 |
| Opinion (think tanks) | 10 |
| Gremial | 8 |

## Stack técnico

- **PyTorch Lightning + Hydra** — entrenamiento y configuración
- **transformers** — 4 encoders del OE2 (BETO / ConfliBERT / XLM-R / XLNet-TBD)
- **Trafilatura** — extracción robusta de artículos
- **Gemini API** — silver labels + filter LLM (con escalado auto)
- **torchmetrics** — Precision / Recall / F1 Macro / Accuracy / Confusion Matrix
- **Plotly** — heatmap interactivo
- **DVC** — versionado de `data/`

## Convenciones de código

- Python >= 3.10
- Linter: ruff
- Tests: pytest (en `tests/`)
- Idioma del código: inglés (clases, funciones, variables)
- Idioma de docs/comentarios: español donde aporta contexto político
