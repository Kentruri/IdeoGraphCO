# CLAUDE.md — IdeoGraphCO

## Proyecto

**Clasificador multiclase probabilístico** de ideología política en noticias
colombianas. Trabajo de grado universitario.

Cada artículo se asigna a **una** de 8 clases ideológicas (single-label,
mutuamente excluyentes). El modelo devuelve una distribución de probabilidades
sobre las 8 clases; la salida se visualiza como **mapa de calor** (no radar).

> Diseño previo: era regresión multisalida sobre 8 ejes en `[0,1]⁸`. Se
> migró a clasificador multiclase por requisito del anteproyecto aprobado.
> Ver `docs/preguntas-director.md` (varios temas ya RESUELTOS ago-2026:
> XLNet, pares de clases; sigue abierto el de la cabeza de politicidad).

## El anteproyecto (contrato de la tesis)

Documento aprobado: *"Desarrollo de clasificador multiclase para
identificación de orientación ideológica en noticias políticas colombianas"*
(Univalle, jun-2026; director: Raúl Gutiérrez de Piñerez). Es la fuente de
verdad ante cualquier duda de diseño — el jurado califica contra él.

**Pregunta de investigación**: ¿de qué manera el desarrollo y evaluación de
un clasificador multiclase, entrenado a partir de un corpus anotado de
noticias políticas colombianas, permite identificar la orientación
ideológica mediante ocho clases y presentar los resultados en un prototipo
interactivo?

**Objetivos específicos y productos comprometidos**:

| OE | Compromiso | Productos |
|----|-----------|-----------|
| OE1 | Corpus: scraping + refinamiento + etiquetado Gold/Silver según codebook | P1.1 scraper con dedup y limpieza · P1.2 codebook operacional · P1.3 dataset Gold+Silver con métricas de concordancia DOCUMENTADAS |
| OE2 | Benchmarking BETO / XLNet / XLM-RoBERTa / ConfliBERT-Spanish + segmentación + Softmax | P2.1 reporte con métricas por clase y análisis de varianza (multi-seed) · P2.2 modelo fine-tuned empaquetado · P2.3 componente de chunking validado |
| OE3 | Evaluar con Precision, Recall, F1 Macro sobre el conjunto de pruebas | P3.1 reporte con matrices de confusión por categoría y análisis de errores |
| OE4 | Prototipo web interactivo con el pipeline de inferencia | P4.1 prototipo que muestra la noticia, la clase predicha y la distribución de probabilidad (repos IdeoGraphCO-FE / IdeoGraphCO-BE) |

**Alcance declarado**:
- Dominio temático ESTRICTO: noticias políticas de Colombia (electoral,
  legislativo, política exterior, gobernanza). Se excluye farándula y lo
  judicial que no impacte la agenda pública — eso implementa el filter LLM.
- SOLO prensa colombiana (decisión reforzada ago-2026 con auditoría de
  colombianidad: medir % de contenido colombiano antes de añadir fuentes).
- Una sola distribución Softmax de dimensión 8 que suma 1.0 (single-label);
  las posturas macroeconómicas se asumen subsumidas en las 8 clases, no son
  clases aparte.

**Protocolo de anotación comprometido** (Krippendorff α = 1 − D_o/D_e):
- Gold: los DOS investigadores anotan una muestra de forma independiente;
  α ≥ 0.8 → discrepancias por consenso; α < 0.8 → iterar el codebook.
- Silver: LLM-judge sigue el codebook; auditoría CONTINUA sobre muestras
  aleatorias midiendo α entre el judge y el consenso de los investigadores.
  Ese α documentado es parte del producto P1.3, no opcional.

**Limitaciones declaradas** (citarlas, no resolverlas): subjetividad residual
del ground truth (el modelo aprende un consenso intersubjetivo, no una
"verdad"); dilución de señal por la agregación vectorial (encuadres agudos
localizados en un párrafo pueden atenuarse en V_doc).

## Las 8 clases ideológicas (4 ejes teóricos del anteproyecto §5.3)

La taxonomía se alinea con el **V-Party Dataset de V-Dem** — el emparejamiento
correcto es el de los ejes, no el "intuitivo" (aquí hubo un bug: el código
tenía los compañeros de los dos primeros ejes intercambiados hasta ago-2026):

| Eje teórico | Par | Anclaje V-Party |
|-------------|-----|-----------------|
| Gobernanza y discurso estamental | Populismo ↔ Institucionalismo | retórica populista (anti-élite) vs. compromiso con el pluralismo |
| Estructura de liderazgo político | Personalismo ↔ Doctrinarismo | control individual del líder sobre la estructura partidaria |
| Política exterior | Soberanismo ↔ Globalismo | nacionalismo económico vs. internacionalismo/multilateralismo |
| Sociocultural | Conservadurismo ↔ Progresismo | derechos civiles, diversidad de género, secularismo |

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
  `xlnet-base-cased` (XLNet original en inglés; decisión ago-2026 de mantener
  el modelo comprometido en el anteproyecto — su bajo desempeño esperado en
  español es hallazgo del benchmark, no un error).
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
│   ├── sources.py         # 434 fuentes colombianas en 7 categorías
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

## Fuentes (434 en 7 categorías — todas colombianas)

`src/scraper/sources.py` — distribución actual (ampliaciones + auditoría de
colombianidad, ago-2026; los medios extranjeros que "cubrían Colombia" se
dieron de baja tras medir que su contenido era mayormente de otros países):

| Categoría | # |
|-----------|---|
| Institucional | 139 |
| Regional | 99 |
| Gremial | 61 |
| Opinion (think tanks) | 53 |
| Independiente | 42 |
| Nacional | 24 |
| Judicial | 16 |

## Stack técnico

- **PyTorch Lightning + Hydra** — entrenamiento y configuración
- **transformers** — 4 encoders del OE2 (BETO / ConfliBERT / XLM-R / XLNet)
- **Trafilatura** — extracción robusta de artículos
- **Gemini API** — silver labels + filter LLM (con escalado auto). El filtro
  devuelve `category` + `confidence` + **`text_issues`**: los issues
  `digest_multinoticia` / `truncado` / `preview_paywall` DESCARTAN el artículo
  (rompen el supuesto single-label o no traen cuerpo), y
  `boilerplate_residual` solo se registra — es la señal para mejorar
  `cleaner.py`, visible en `scripts/analyze_filter_log.py`
- **torchmetrics** — Precision / Recall / F1 Macro / Accuracy / Confusion Matrix
- **Plotly** — heatmap interactivo
- **DVC** — versionado de `data/`

## Convenciones de código

- Python >= 3.10
- Linter: ruff
- Tests: pytest (en `tests/`)
- Idioma del código: inglés (clases, funciones, variables)
- Idioma de docs/comentarios: español donde aporta contexto político
