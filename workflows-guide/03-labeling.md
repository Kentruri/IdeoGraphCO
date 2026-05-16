# Paso 3 — Etiquetado con LLM-as-a-Judge

## Qué hace

Usa **Gemini** como anotador automático para asignar a cada artículo:
- `is_political`: 1 si es político, 0 si no
- 8 scores ideológicos de 0 a 1 (uno por cada eje del modelo)

## Concepto: LLM-as-a-Judge

En vez de que humanos etiqueten miles de artículos manualmente (carísimo y lento), instruimos a un LLM con un **codebook** (manual de criterios) y le pedimos que califique cada artículo siguiendo esas reglas.

Las labels resultantes se llaman **silver standard** (no "gold" porque no las hizo un experto humano), pero son consistentes y reproducibles.

## Los 8 ejes ideológicos

| Eje | Opuesto | Marca |
|-----|---------|-------|
| **Personalismo** | Institucionalismo | Foco en líderes individuales |
| **Institucionalismo** | Personalismo | Léxico jurídico, procesos formales |
| **Populismo** | Doctrinarismo | Dicotomía pueblo vs. élite |
| **Doctrinarismo** | Populismo | Rigidez teórica, "ismos" |
| **Soberanismo** | Globalismo | Autonomía nacional, proteccionismo |
| **Globalismo** | Soberanismo | Tratados, multilateralismo |
| **Conservadurismo** | Progresismo | Orden tradicional, autoridad |
| **Progresismo** | Conservadurismo | Reformas sociales, derechos |

**Importante**: los ejes opuestos NO son mutuamente excluyentes. Un artículo puede ser alto en personalismo Y alto en institucionalismo (ej: "Petro firmó un decreto").

## Cómo funciona

Por cada artículo, el script:

1. Lee el texto del JSONL
2. Construye un **system prompt** con el codebook (definiciones, marcadores, reglas)
3. Envía el texto a Gemini API
4. Gemini devuelve un JSON con los 9 campos (is_political + 8 ejes)
5. El script normaliza scores 0-100 → 0-1
6. Guarda en `data/interim/labeled_news.jsonl`

## Archivos involucrados

- [src/labeling/codebook.py](../src/labeling/codebook.py) — Codebook completo (definiciones, marcadores, escalas, ejemplos, reglas)
- [src/labeling/judge.py](../src/labeling/judge.py) — Pipeline de llamadas a Gemini con retry y cursor
- [scripts/label.py](../scripts/label.py) — CLI principal

## Setup previo

```bash
# 1. Obtener API key gratis
# https://aistudio.google.com → Get API Key

# 2. Configurar en .env
echo "GEMINI_API_KEY=AIzaSy..." > .env

# 3. Verificar que carga
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(bool(os.environ.get('GEMINI_API_KEY')))"
```

### Activar billing (recomendado)

El tier gratuito tiene **20 RPD** (requests por día) — insuficiente para etiquetar miles de artículos.

Con billing activado:
- Rate limit sube a 1000+ RPD
- Costo real: **~COP 1.4 por artículo**
- Para 1,300 artículos: ~COP 1,800 (~$0.45 USD)

Para activar: ve a https://aistudio.google.com/app/apikey → "Set up billing" → prepago COP 40,000 mínimo.

## Comandos

```bash
source .venv/bin/activate

# Probar con 5 artículos
python scripts/label.py --max-articles 5

# Etiquetar todo
python scripts/label.py --model gemini-2.5-flash-lite

# Re-etiquetar desde cero
python scripts/label.py --force

# Cambiar modelo
python scripts/label.py --model gemini-2.5-flash
```

### Parámetros

- `--max-articles N` — Límite de artículos (default: todos)
- `--force` — Re-etiquetar desde cero (ignora cursor)
- `--model MODELO` — Modelo de Gemini (default: `gemini-2.5-flash-lite`)
- `--input ARCHIVO` — JSONL de entrada (default: `data/raw/news_clean.jsonl`)

## Modelos disponibles

| Modelo | Costo / 1M tokens | Recomendación |
|--------|------------------|---------------|
| `gemini-2.5-flash-lite` | $0.075 in, $0.30 out | ✅ Default — sweet spot |
| `gemini-2.5-flash` | $0.30 in, $2.50 out | Para validación cruzada |
| `gemini-2.5-pro` | $1.25 in, $10 out | Overkill para esta tarea |

Para el codebook estructurado de IdeoGraphCO, **Flash Lite es suficiente**.

## Salida

`data/interim/labeled_news.jsonl` — Una línea por artículo con scores:

```json
{
  "text": "El presidente anunció...",
  "title": "Reforma tributaria genera debate",
  "source": "eltiempo",
  "category": "nacional",
  "url": "https://...",
  "date": "2026-03-25",
  "is_political": 1,
  "personalismo": 0.75,
  "institucionalismo": 0.4,
  "populismo": 0.6,
  "doctrinarismo": 0.2,
  "soberanismo": 0.1,
  "globalismo": 0.1,
  "conservadurismo": 0.4,
  "progresismo": 0.5
}
```

## El codebook

Vive en [src/labeling/codebook.py](../src/labeling/codebook.py) y tiene 3 secciones:

**1. AXIS_DEFINITIONS** — Por cada eje:
- `definition` — Qué significa
- `markers` — Pistas lingüísticas a buscar
- `scale` — Calibración 0-100 con descripciones
- `examples_high` y `examples_low` — Fragmentos calibrados de ejemplo

**2. CALIBRATION_RULES** — 7 reglas globales:
- Evaluar solo lo que dice el texto explícitamente
- Los 8 puntajes son independientes
- Los ejes opuestos NO son mutuamente excluyentes
- Filtrar primero por politicidad
- Medir intensidad retórica, no postura
- Considerar el contexto colombiano (paz, conflicto, etc.)
- Devolver solo JSON puro

**3. build_system_prompt()** — Ensambla todo en un prompt para Gemini.

Si quieres ajustar el comportamiento del LLM, edita el codebook y vuelve a correr con `--force`.

## Cursor incremental

`data/interim/.label_cursor` guarda la línea del último artículo etiquetado. Si se interrumpe el proceso:
- Volver a correr el comando continúa donde quedó
- No se gasta API en artículos ya etiquetados

## Tiempo y costo

| Cantidad | Tiempo | Costo aprox |
|----------|--------|-------------|
| 5 (prueba) | ~30 seg | ~COP 7 |
| 100 | ~3 min | ~COP 140 |
| 1,300 | ~30 min | ~COP 1,800 |
| 5,000 | ~2 horas | ~COP 7,000 |
| 20,000 | ~8 horas | ~COP 28,000 |

Con `gemini-2.5-flash-lite` y rate limit de 1.5s entre requests.

## Logs de salida

```
2026-05-05 12:34:56 INFO Artículos: 1287 total | 0 ya etiquetados | 1287 pendientes
2026-05-05 12:34:56 INFO Rate limit: 1.5s entre requests (~40 RPM)
2026-05-05 12:34:56 INFO   Etiquetados: 10/1287 (errores: 0)
2026-05-05 12:35:12 INFO   Etiquetados: 20/1287 (errores: 0)
...
```

## Solución de problemas

### Error 429 (rate limit) en free tier
Con tier gratuito tienes 20 RPD. Activar billing (ver setup arriba) o reducir a `--max-articles 20`.

### Modelo no existe
Lista modelos disponibles:
```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from google import genai
client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
for m in client.models.list():
    if 'generateContent' in m.supported_actions:
        print(m.name)
"
```

### Scores raros
Indica codebook ambiguo. Mejorar definiciones/ejemplos en `codebook.py` y volver a correr con `--force`.

## Cuándo correrlo

- **Después del cleaning** (paso 2)
- **Antes del filtering** (paso 4)

## Validación cruzada (opcional)

Para fortalecer la metodología de la tesis:
```bash
# Re-etiquetar 50 al azar con un modelo más capaz
python scripts/label.py --model gemini-2.5-flash --max-articles 50 \
    --output data/interim/labeled_news_validation.jsonl
```

Luego comparar correlación de scores entre los dos modelos.
