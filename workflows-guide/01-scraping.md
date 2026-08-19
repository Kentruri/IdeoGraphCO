# 1 — Scraping (con clean + filter LLM)

Un solo comando descarga, limpia y filtra artículos políticos. Solo
`political_article` (según el LLM filter) llega al archivo final.

## Comando

```bash
python scripts/scraper.py
```

## Flags útiles

- `--max-articles N` — N por fuente (default 50)
- `--sources eltiempo lasillavacia` — solo esas fuentes
- `--categories nacional independiente` — categorías a scrapear
- `--no-filter` — solo scrape+clean (no gasta API)
- `--escalate-threshold 0.6` — umbral del escalado del filter
- `--no-escalate` — desactiva escalado al modelo grande
- `--log-level DEBUG` — logs verbose
- `--workers 6` — fuentes en paralelo (extracción ~5x más rápida; el LLM
  sigue serializado por el rate limiter global)
- `--gdelt` — suma candidatos frescos de GDELT DOC 2.0 (gratis); dominios
  fuera del catálogo van a `logs/gdelt_unknown_domains.jsonl` (curaduría)
- `--prefilter` — cascada local antes del LLM (casos obvios gratis).
  Entrenar con `python scripts/train_prefilter.py` cuando el filter-log
  acumule decisiones (ahora guarda `text_head` para eso)

## Output

| Archivo | Contenido |
|---------|-----------|
| `data/raw/articles.jsonl` | Artículos políticos limpios (text, title, source, category, url, id, ...) |
| `logs/filter_decisions.jsonl` | Decisión del filtro por URL (engine llm/prefilter, kept, category, confidence, escalated, `text_head` — dataset del prefilter) |
| `data/scraper_history.db` | SQLite con URLs/content_hash ya vistos (dedup persistente) |

## Componentes

- [scripts/scraper.py](../scripts/scraper.py) — CLI
- [src/scraper/pipeline.py](../src/scraper/pipeline.py) — orquesta scrape→clean→filter
- [src/scraper/sources.py](../src/scraper/sources.py) — 434 fuentes colombianas en 7 categorías
- [src/scraper/prompts.py](../src/scraper/prompts.py) — `FILTER_SYSTEM_PROMPT` aislado
- [scripts/analyze_filter_log.py](../scripts/analyze_filter_log.py) — análisis del log de decisiones
- [scripts/train_prefilter.py](../scripts/train_prefilter.py) — entrena el prefilter local (teacher→student)
- [scripts/analyze_class_balance.py](../scripts/analyze_class_balance.py) — clase × fuente (scraping dirigido)
