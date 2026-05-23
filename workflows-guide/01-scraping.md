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

## Output

| Archivo | Contenido |
|---------|-----------|
| `data/raw/articles.jsonl` | Artículos políticos limpios (text, title, source, category, url, id, ...) |
| `logs/filter_decisions.jsonl` | Decisión del filter LLM por URL (kept/dropped, category, confidence, escalated) |
| `data/scraper_history.db` | SQLite con URLs/content_hash ya vistos (dedup persistente) |

## Componentes

- [scripts/scraper.py](../scripts/scraper.py) — CLI
- [src/scraper/pipeline.py](../src/scraper/pipeline.py) — orquesta scrape→clean→filter
- [src/scraper/sources.py](../src/scraper/sources.py) — 83 fuentes en 7 categorías
- [src/scraper/prompts.py](../src/scraper/prompts.py) — `FILTER_SYSTEM_PROMPT` aislado
- [scripts/analyze_filter_log.py](../scripts/analyze_filter_log.py) — análisis del log de decisiones
