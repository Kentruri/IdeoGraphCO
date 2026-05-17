# Pipeline IdeoGraphCO

## Orden

1. **Scraping** — descarga noticias de medios colombianos
2. **Cleaning** — regex remueve CTAs, cookies, paywalls
3. **Filtering** — LLM barato descarta basura, biografías, páginas estáticas
4. **Labeling** — LLM caro etiqueta los 8 ejes (escala 1-5)
5. **Gold set humano** — anotación manual de ~150 artículos hold-out (test)
6. **Splits** — train/val pre-computados a disco, gold como test
7. **Training / Benchmark** — ConfliBERT + 8 cabezas (Lightning + Hydra)
8. **Inference** — predice 8 scores + radar chart

## Por qué filter va ANTES que label

Labeling cuesta ~4x más por llamada que filtering (`gemini-2.5-flash` vs `gemini-2.5-flash-lite`) y se necesitan ambas etapas. Filtrar primero evita pagar por etiquetar artículos que después se descartan.

## Comandos

```bash
source .venv/bin/activate

# 1. Scraping (~2-4 h, gratis)
python scripts/scraper.py

# 2. Cleaning regex (segundos)
python scripts/clean.py

# 3. Filtering basura con LLM (~25 min, ~COP 250)
python scripts/filter_articles.py

# 4. Labeling con escala 1-5 (~20 min, ~COP 1,000)
python scripts/label.py

# 5. Gold set humano (manual, ~6-10 h con el PDF de bitácora)
python scripts/prepare_gold_set.py     # muestreo estratificado → CSV
# (editar el CSV a mano con el PDF)
python scripts/finalize_gold_set.py    # CSV → test_gold.jsonl

# 6. Pre-computar splits train/val (segundos)
python scripts/prepare_splits.py

# 7a. Training de un modelo
python -m src.training.train

# 7b. Benchmark de 3 encoders × 3 semillas (~18-24 h en Mac)
python scripts/benchmark.py --seeds 42 43 44
python scripts/compare_models.py

# 8. Inferencia
python -m src.inference.predict --text "..."
```
