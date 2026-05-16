# Paso 1 — Scraping de noticias políticas

## Qué hace

Descarga noticias políticas colombianas de **30+ medios** y guarda el texto plano en `data/raw/news.jsonl`. Cada línea es un artículo con metadatos (URL, fuente, fecha, autores).

## Cómo funciona

Tres estrategias por fuente, en orden de prioridad:

1. **RSS feeds** (más limpio) — Para medios con feeds políticos (`/rss/politica.xml`)
2. **Sitemap + filtro** — Para medios con `/sitemap.xml`, filtrando URLs por sección política (`/politica/`, `/economia/`, `/nacion/`)
3. **Crawl directo** — Para medios sin RSS ni sitemap, extraer links de la página principal

Características del scraper:
- **Trafilatura** para extracción limpia de texto (mejor que Newspaper4k)
- **User-Agents rotativos** (Chrome, Firefox, Safari) para evitar bloqueos
- **Backoff exponencial** ante errores
- **SQLite** para deduplicación entre ejecuciones
- **robots.txt** respetado por defecto

## Archivos involucrados

- [src/data/sources.py](../src/data/sources.py) — Catálogo de 30+ fuentes (URL, categoría, mode, RSS feeds)
- [src/data/scraping/parser.py](../src/data/scraping/parser.py) — Extracción con trafilatura
- [src/data/scraping/config.py](../src/data/scraping/config.py) — User-Agents y headers
- [src/data/scraping/db.py](../src/data/scraping/db.py) — Deduplicación SQLite
- [src/data/scraping/robots.py](../src/data/scraping/robots.py) — Verificación robots.txt
- [scripts/scraper.py](../scripts/scraper.py) — CLI principal

## Comandos

```bash
source .venv/bin/activate

# Mantener el Mac despierto durante el scraping
caffeinate -d -i -s &

# Scrapear todas las fuentes (max 100 por fuente)
python scripts/scraper.py --max-articles 100

# Solo categorías específicas
python scripts/scraper.py --categories nacional independiente --max-articles 50

# Solo fuentes individuales
python scripts/scraper.py --sources eltiempo lasillavacia --max-articles 30
```

### Parámetros

- `--max-articles N` — Máximo de artículos por fuente (default: 50)
- `--categories LISTA` — Solo categorías específicas: nacional, independiente, regional, institucional, gremial, opinion
- `--sources LISTA` — Solo fuentes individuales (ej: eltiempo, semana)
- `--output ARCHIVO` — Archivo de salida (default: `data/raw/news.jsonl`)

## Categorías de fuentes

| Categoría | # Fuentes | Ejemplos |
|-----------|-----------|----------|
| **nacional** | 8 | El Tiempo, El Espectador, Semana, Portafolio |
| **independiente** | 11 | La Silla Vacía, Cambio, Vorágine, Razón Pública |
| **opinion** | 3 | Dejusticia, PARES, Latinoamérica21 |
| **institucional** | 9 | Presidencia, Senado, Cámara, Cancillería |
| **regional** | 6 | El Colombiano, El Heraldo, El País Cali |
| **gremial** | 3 | FECODE, ANDI, Valores Cristianos |

Catálogo completo en [src/data/sources.py](../src/data/sources.py).

## Salida

`data/raw/news.jsonl` — Una línea JSON por artículo:

```json
{
  "text": "El presidente anunció una reforma...",
  "title": "Reforma tributaria genera debate",
  "authors": ["Juan Pérez"],
  "source": "eltiempo",
  "category": "nacional",
  "url": "https://www.eltiempo.com/politica/...",
  "date": "2026-03-25",
  "scraped_at": "2026-03-26T12:34:56+00:00"
}
```

## Tiempo y costo

- **Tiempo**: 2-4 horas para ~1,000-2,000 artículos
- **Costo**: gratis (no usa LLM)
- **Cuota**: limitado por el rate limiting del scraper (1-3s entre descargas)

## Comportamiento ante interrupciones

El scraper guarda **incrementalmente** cada artículo en `data/raw/news.jsonl`:
- Si se cae a la mitad, los artículos previos están guardados
- La SQLite (`data/scraper_history.db`) recuerda URLs ya descargadas
- Volver a correr el mismo comando salta lo ya descargado y continúa

## Logs

Cada URL procesada genera una línea en el log:

```
[eltiempo] OK   2358 chars — https://www.eltiempo.com/politica/...
[eltiempo] DUP  https://www.eltiempo.com/...    (ya en BD)
[eltiempo] FAIL https://www.eltiempo.com/...    (texto < 400 chars)
[eltiempo] ROBOT https://www.eltiempo.com/...   (bloqueado por robots.txt)
```

## Solución de problemas

### "No se encontraron URLs para X"
La fuente no tiene RSS, sitemap, ni links extraíbles del homepage. Saltar esa fuente o añadir su URL específica de sección política a `sources.py`.

### Errores 429 (rate limit)
El backoff exponencial maneja esto automáticamente. Si persiste, aumentar el delay base en `parser.py`.

### "Sitemap timeout"
Algunos medios tienen sitemaps gigantes. El timeout de 30s es razonable; si una fuente siempre falla, añadirla con `mode: "direct"` y RSS.

## Volumen recomendado

- **Prueba**: `--max-articles 5` (~10 minutos)
- **Mediano**: `--max-articles 50` (~1 hora)
- **Para tesis**: `--max-articles 100` (~2-3 horas, ~1,300 artículos)
- **Ambicioso**: `--max-articles 200` (~6 horas, ~3,000 artículos)

## Desactivar caffeinate al terminar

```bash
pkill caffeinate
```
