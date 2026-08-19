# Pipeline IdeoGraphCO

Clasificador multiclase: noticia → **1 de 8 clases ideológicas** + distribución
probabilística → mapa de calor.

## Etapas

| # | Etapa | Comando | Output |
|---|-------|---------|--------|
| 1 | Scrape + clean + filter LLM | `python scripts/scraper.py` | `data/raw/articles.jsonl` |
| 2 | Labeling silver categórico (LLM) | `python scripts/label.py --input data/raw/articles.jsonl` | `data/silver/silver_set.jsonl` (`label` + 8 scores) |
| 3 | Gold set v2 (libros por anotador con solape) | `python scripts/prepare_gold_set.py --annotators kevin juan` | `annotation/gold_set_v2_<anotador>.xlsx` |
| 3b | Ingesta gold + **Krippendorff α** + consenso | `python scripts/ingest_gold.py --books ... --audit-silver data/silver/silver_set.jsonl` | `annotation/gold_set_v2_labeled.jsonl` + reporte α |
| 4 | Dataset canónico + splits por ID (test = gold HUMANO) | `python scripts/prepare_splits.py --gold-labeled annotation/gold_set_v2_labeled.jsonl` | `data/processed/dataset.jsonl` + `splits.json` |
| 5 | Training de 1 modelo | `python -m src.training.train` | `logs/checkpoints/<alias>/best.ckpt` |
| 5b | Benchmark (selección en VALIDACIÓN) | `python scripts/benchmark.py --seeds 42 43 44` | `reports/benchmark_report.md` |
| 6 | **Evaluación final en test — UNA vez, con el ganador** (P3.1) | `python scripts/final_eval.py --checkpoint logs/checkpoints/<alias>/best.ckpt` | `reports/evaluacion_final.md` (por clase + confusión + errores) |
| 7 | Inferencia local | Ver `workflows-guide/08-inference.md` | mapa de calor HTML |
| 7b | Servicio de inferencia (para IdeoGraphCO-BE) | `IDEOGRAPH_CHECKPOINT=... uvicorn src.inference.api:app --port 8080` | `POST /classify`, `POST /delta`, `GET /health` |

## Notas clave

- **Filter LLM aguas arriba**: la etapa 1 descarta artículos no-políticos con
  Gemini (categorías `nonpolitical_article`, `biography_static`, `garbage`).
  Solo `political_article` continúan al modelo.
- **Scraper (mejoras)**: frescura primero (RSS → news-sitemaps con fecha →
  GDELT opcional con `--gdelt` → sitemap histórico), URLs normalizadas
  (sin `utm_*`), paralelización con `--workers N` (LLM serializado por rate
  limiter global), y **prefilter local** (`--prefilter`, cascada
  teacher→student: TF-IDF+LR entrenado con las decisiones del propio LLM
  vía `scripts/train_prefilter.py` — el filter-log ahora guarda `text_head`
  para eso). Las URLs solo se marcan procesadas en desenlaces definitivos:
  fallos de scraping o del LLM se reintentan en la siguiente corrida.
  Balance de clases por fuente: `scripts/analyze_class_balance.py`
  (scraping dirigido a clases minoritarias).
- **Calidad del corpus**: compuerta estructural gratuita
  (`src/scraper/quality.py`) que rechaza páginas de listado/sección y
  prosa rota ANTES del filtro LLM (contadores `low_quality:*`). Auditar
  o reparar un corpus existente: `scripts/audit_corpus_quality.py --fix`.
- **Dedup en dos capas**: `scraper_history.db` (URL normalizada + hash de
  contenido, WAL thread-safe) y guardia por ID contra el JSONL de salida
  (si la BD se pierde, la salida igual no se duplica). Re-correr el
  scraper solo trae noticias nuevas.
- **Silver categórico**: el judge asigna la clase **dominante** (`label` +
  `label_idx`, metodología del anteproyecto) y conserva los 8 scores de
  intensidad como señal secundaria. El silver viejo (solo 8 floats) sigue
  siendo legible vía argmax, pero está deprecado: re-etiquetar con
  `python scripts/label.py --force`.
- **Gold humano v2**: escalas 1-5 por eje + `clase_dominante` obligatoria.
  Doble anotación independiente sobre un bloque de solape → Krippendorff
  α ≥ 0.8 (umbral del anteproyecto); discrepancias por consenso
  (`scripts/ingest_gold.py`).
- **Protocolo de evaluación**: el benchmark compara modelos con métricas de
  **validación** (corre con `+run_test=false`); el test/gold se toca UNA sola
  vez con el modelo ganador (`scripts/final_eval.py`). Así el gold no se
  contamina por selección.
- **Splits v2**: por ID (no por índice), estratificados por clase, con guardia
  anti-fuga (near-duplicados del test excluidos de train/val) y verificación
  de que el test lleve etiquetas humanas (`--allow-silver-test` solo para
  desarrollo).
- **Cabeza binaria de politicidad**: fuera del modelo neural (la cumple el
  filter LLM aguas arriba). Ver `docs/preguntas-director.md` tema 1.
- **Escalado automático del filter**: si `gemini-2.5-flash-lite` da
  `confidence < 0.7`, re-llama a `gemini-2.5-flash`.
- **Chunking**: artículos largos se dividen en K chunks de 512 tokens con
  stride 384; el modelo promedia los embeddings `[CLS]` antes de la cabeza
  softmax. `max_chunks=8` limita memoria en artículos muy largos.
- **ΔD (P5.2)**: `src/inference/delta.py` — distancia de Jensen-Shannon
  (default, ∈ [0,1]) entre dos distribuciones de 8 clases; alternativas
  Hellinger y variación total. Expuesta también en `POST /delta`.

## Decisiones pendientes

Ver [docs/preguntas-director.md](docs/preguntas-director.md).

Más detalle por etapa: [workflows-guide/](workflows-guide/).
