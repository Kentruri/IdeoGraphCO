# Pipeline IdeoGraphCO

Clasificador multiclase: noticia → **1 de 8 clases ideológicas** + distribución
probabilística → mapa de calor.

## Etapas

| # | Etapa | Comando | Output |
|---|-------|---------|--------|
| 1 | Scrape + clean + filter LLM | `python scripts/scraper.py` | `data/raw/articles.jsonl` |
| 2 | Labeling silver (LLM) | `python scripts/label.py --input data/raw/articles.jsonl` | `data/silver/silver_set.jsonl` |
| 3 | Gold set (Excel para anotación humana) | `python scripts/prepare_gold_set.py` | `annotation/gold_set_v1.xlsx` |
| 4 | Splits (test=gold, train/val=resto) | `python scripts/prepare_splits.py` | `data/processed/splits.json` |
| 5 | Training de 1 modelo | `python -m src.training.train` | `logs/checkpoints/<alias>/best.ckpt` |
| 5b | Benchmark de N encoders × M semillas | `python scripts/benchmark.py --seeds 42 43 44` | `reports/benchmark_report.md` |
| 6 | Inferencia | Ver `workflows-guide/08-inference.md` | mapa de calor HTML |

## Notas clave

- **Filter LLM aguas arriba**: la etapa 1 descarta artículos no-políticos con
  Gemini (categorías `nonpolitical_article`, `biography_static`, `garbage`).
  Solo `political_article` continúan al modelo.
- **Silver actual = continuo (legacy)**: `silver_set.jsonl` contiene 8 floats
  por artículo (herencia del diseño previo de regresión). El Dataset convierte
  con `argmax` al vuelo al ID de clase (`src.core.schema.CLASS_TO_IDX`). Ver
  `docs/preguntas-director.md` tema 5 para la decisión de re-etiquetado.
- **Gold humano**: enteros 1-5 en 8 columnas del Excel. Se convierten a
  `label_idx = argmax(scores)` (tema 3 de las preguntas).
- **Cabeza binaria de politicidad**: fuera del modelo neural (la cumple el
  filter LLM aguas arriba). Ver `docs/preguntas-director.md` tema 1.
- **Escalado automático del filter**: si `gemini-2.5-flash-lite` da
  `confidence < 0.7`, re-llama a `gemini-2.5-flash`.
- **Chunking**: artículos largos se dividen en K chunks de 512 tokens con
  stride 384; el modelo promedia los embeddings `[CLS]` antes de la cabeza
  softmax. `max_chunks=8` limita memoria en artículos muy largos.

## Decisiones pendientes

Ver [docs/preguntas-director.md](docs/preguntas-director.md).

Más detalle por etapa: [workflows-guide/](workflows-guide/).
