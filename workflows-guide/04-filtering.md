# Paso 4 — Filtrado de basura con LLM

## Qué hace

Pasa por **Gemini** cada artículo etiquetado y descarta los que NO son artículos de noticia reales. Captura casos que el regex del cleaner no puede detectar.

## Por qué este paso es necesario

Después del scraping y la limpieza con regex, todavía pueden quedar:

| Caso | Ejemplo |
|------|---------|
| **Sitemaps en bruto** | Lista de URLs y timestamps sin texto editorial |
| **Glosarios** | "Diccionario legislativo" del Senado con citas legales |
| **Páginas estáticas** | "Quiénes somos", "Misión y visión" |
| **Biografías** | Perfiles de periodistas o columnistas |
| **Listas de documentos** | "Documentos 2026" con títulos sueltos |
| **Restos de UI** | Cookie banners cortados que el regex no atrapó |

El LLM puede identificar estos casos contextualmente — el regex no.

## Cómo funciona

Por cada artículo en `data/interim/labeled_news.jsonl`:

1. **Aplica el cleaner mejorado** (regex) sobre el texto
2. **Si quedó < 300 chars** → descartar sin gastar LLM
3. **Pregunta al LLM**: ¿Es esto un artículo real o basura?
4. **Si es basura** → descartar
5. **Si es real** → guardar con texto limpio en `labeled_news_clean.jsonl`

## Categorías que el LLM identifica

El LLM clasifica cada texto en una de 5 categorías:

| Categoría | Decisión | Ejemplo |
|-----------|----------|---------|
| `article` | ✅ Conservar | Artículo de noticia bien formado |
| `garbage` | ❌ Descartar | Menú, sitemap, lista de URLs |
| `biography` | ❌ Descartar | Biografía de un periodista |
| `static_page` | ❌ Descartar | "Acerca de", "Quiénes somos" |
| `other` | ❌ Descartar | Recetas, horóscopo, deportes |

## Archivos involucrados

- [src/labeling/article_filter.py](../src/labeling/article_filter.py) — `is_real_article()` con prompt para Gemini
- [src/data/scraping/cleaner.py](../src/data/scraping/cleaner.py) — Cleaner mejorado con patrones para restos de cookies
- [scripts/filter_articles.py](../scripts/filter_articles.py) — CLI principal

## Setup previo

Igual que el paso 3 — necesita `GEMINI_API_KEY` en `.env` y billing activado.

## Comandos

```bash
source .venv/bin/activate

# Prueba rápida (solo reporta, no escribe)
python scripts/filter_articles.py --max-articles 10 --dry-run

# Prueba real con 10 artículos
python scripts/filter_articles.py --max-articles 10

# Filtrar todo
python scripts/filter_articles.py --model gemini-2.5-flash-lite

# Re-filtrar desde cero
python scripts/filter_articles.py --force
```

### Parámetros

- `--max-articles N` — Límite de artículos (default: todos)
- `--dry-run` — Solo reporta, no escribe el archivo
- `--force` — Re-filtrar desde cero (ignora cursor)
- `--model MODELO` — Modelo de Gemini (default: `gemini-2.5-flash-lite`)
- `--rate-limit SEG` — Delay entre requests (default: 1.5s)

## Salida

`data/interim/labeled_news_clean.jsonl` — Mismo formato que `labeled_news.jsonl` pero solo con artículos que el LLM clasificó como `article`. Texto post-cleaner.

## Cursor incremental

`data/interim/.filter_cursor` guarda la línea del último artículo procesado. Si se interrumpe:
- Volver a correr continúa donde quedó
- No re-gasta API en artículos ya filtrados

## Tiempo y costo

| Cantidad | Tiempo | Costo aprox |
|----------|--------|-------------|
| 10 (prueba) | ~30 seg | ~COP 2 |
| 100 | ~3 min | ~COP 20 |
| 1,300 | ~30 min | ~COP 250 |

Más barato que el labeling porque el filter solo necesita ~200 tokens de input (los primeros 1,500 chars del texto) en vez del artículo completo.

## El system prompt del filter

```
Eres un validador de contenido. Tu tarea es decidir si un texto es un
artículo de noticia colombiano bien formado, o si es basura/contenido no
editorial.

CATEGORÍAS:
- article: Artículo de noticia/opinión real, con párrafos coherentes
- garbage: Menús, listas de URLs, sitemaps, glosarios, formularios
- biography: Biografía o perfil de una persona
- static_page: Página institucional estática
- other: Cualquier otro contenido no noticioso

REGLAS:
1. Si el texto tiene párrafos coherentes con narrativa → "article"
2. Si es sucesión de títulos, fechas y URLs → "garbage"
3. Si describe trayectoria de persona como sujeto → "biography"
4. En caso de duda → "garbage"

FORMATO: solo JSON
{"is_article": true/false, "category": "...", "reason": "..."}
```

## Logs de salida

```
============================================================
  IdeoGraphCO — Filtro de artículos basura
  Modelo: gemini-2.5-flash-lite
  Total entrada: 1287
  Pendientes: 1287
============================================================

  Procesados: 25/1287 | Conservados: 23 | Descartados: 2
  Procesados: 50/1287 | Conservados: 47 | Descartados: 3
  ...

============================================================
  RESULTADO DEL FILTRADO
  Total procesados: 1287
  ✓ Conservados (artículos reales): 1145
  ✗ Descartados (basura): 142

  Distribución de categorías:
    article: 1145
    garbage: 87
    biography: 22
    static_page: 18
    other: 15

  Ejemplos descartados:
    [garbage] https://www.elheraldo.co/arc/outboundfeeds/sitemap/...
      → Lista de URLs sin texto editorial
    [static_page] https://fecode.edu.co/cartillas-abc/
      → Menú de proyectos sin contenido noticioso
============================================================
```

## Diferencia con el cleaner del paso 2

| Paso | Tipo | Qué hace |
|------|------|----------|
| **Paso 2** (cleaning) | Regex | Quita basura DENTRO de artículos (cookie banners, CTAs, firmas) |
| **Paso 4** (filtering) | LLM | Descarta artículos que SON basura completa |

## Solución de problemas

### El LLM clasifica artículos válidos como "garbage"
Es raro pero pasa. Revisar los ejemplos descartados en el log. Si hay falsos positivos sistemáticos, ajustar el prompt en `article_filter.py`.

### Demasiados descartes (>30%)
Posible que el cleaner está dejando muchos artículos cortados/incompletos. Revisar paso 2 primero.

### Costo más alto que esperado
El default toma los primeros 1,500 chars. Si tus artículos son MUY largos, ajustar `max_chars` en `is_real_article()`.

## Cuándo correrlo

- **Después del labeling** (paso 3)
- **Antes de generar el Excel** (paso 5) o **el entrenamiento** (paso 6)

Si modificas el prompt del filter, vuelve a correr con `--force`.
