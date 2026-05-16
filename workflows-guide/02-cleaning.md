# Paso 2 — Limpieza con regex

## Qué hace

Aplica reglas regex para remover **basura editorial** del texto de cada artículo:
- Cookie banners
- Paywalls y prompts de suscripción
- "Frases parásito" como `LEA TAMBIÉN`, `Le puede interesar`
- Firmas de periodista al final
- Emails de contacto
- Footers de marca (PORTAFOLIO, EL TIEMPO, etc.)
- Listings de noticias relacionadas
- Restos de UI legal ("aquí", "Aceptar", etc.)

NO hace clasificación de qué es artículo y qué no — eso lo hace el LLM filter (paso 4).

## Cómo funciona

Aplica 14 patrones regex en orden secuencial sobre cada artículo:

```
0. Marcador de inicio: si hay "Noticia\n"/"Análisis\n", descartar todo lo previo
1. Cookie banner completo
2. Restos de cookie banner
3. Restos de UI legal
4. Paywall / suscripción
5. UI de chatbot y errores
6. Bloques CTA ("LEA TAMBIÉN\n\ntítulo")
7. Frases CTA inline
8. CTAs de WhatsApp/redes sociales
9. Firmas de periodista al final
10. Emails al final
11. Footers de marca
12. Listings ("Más para ver", "BOLETINES EL TIEMPO", etc.)
13. Líneas con solo el nombre del autor
14. Normalización de espacios en blanco
```

**Importante**: NO convierte a minúsculas. ConfliBERT es Cased y los nombres propios importan.

## Filtro de secciones no políticas

Antes de aplicar la limpieza, descarta artículos cuya URL pertenece a secciones claramente no políticas: deportes, entretenimiento, tecnología, loterías, turismo, etc. Lista completa en [scripts/clean.py](../scripts/clean.py).

## Archivos involucrados

- [src/data/scraping/cleaner.py](../src/data/scraping/cleaner.py) — Función `clean_article_text()` con todos los regex
- [scripts/clean.py](../scripts/clean.py) — CLI con cursor incremental

## Comandos

```bash
source .venv/bin/activate

# Limpieza incremental (solo nuevos artículos)
python scripts/clean.py

# Forzar re-limpieza desde cero
python scripts/clean.py --force

# Sin filtro de secciones (mantener deportes, etc.)
python scripts/clean.py --no-filter
```

### Parámetros

- `--force` — Re-limpiar todo desde cero (ignora cursor)
- `--no-filter` — No filtrar por sección (mantener deportes, entretenimiento)

## Salida

`data/raw/news_clean.jsonl` — Mismo formato que `news.jsonl` pero con texto limpio. Artículos que quedan con menos de 300 caracteres post-limpieza son descartados.

## Cursor incremental

`data/raw/.clean_cursor` guarda la línea del último artículo procesado. Al volver a correr:
- Solo procesa artículos nuevos (líneas posteriores al cursor)
- Termina rápido si no hay nada nuevo

## Tiempo y costo

- **Tiempo**: segundos (regex puro)
- **Costo**: gratis

## Ejemplo de limpieza

**Antes:**
```
En este portal utilizamos datos de navegación / cookies propias y de terceros...
Si continúa navegando, usted estará aceptando esta utilización.

Noticia
Petro firma decreto sobre reforma agraria
El presidente anunció...

LEA TAMBIÉN
Reforma tributaria genera debate

...continuación del artículo...

Redacción Justicia
Justicia@eltiempo.com
```

**Después:**
```
Petro firma decreto sobre reforma agraria
El presidente anunció...

...continuación del artículo...
```

## Limitaciones

El cleaner es **solo regex**, así que no puede:
- Detectar artículos completamente basura (sitemaps, glosarios) — lo hace el LLM filter (paso 4)
- Reescribir texto mal formado
- Decidir si un texto es noticia o no

Para esos casos, el [paso 4 de filtering](04-filtering.md) usa LLM.

## Cuándo correrlo

- **Después del scraping** (paso 1)
- **Antes del labeling** (paso 3)

Si modificas los patrones regex en `cleaner.py`, vuelve a correr con `--force` para re-limpiar todo.
