# Paso 5 — Exportar muestra para el director

## Qué hace

Genera un archivo Excel con **200 artículos por cada ideología** (1,600 filas totales) para que el director pueda revisar la calidad de las labels y el contenido del dataset.

## Estructura del Excel

El archivo `muestra_ideologica.xlsx` tiene **9 hojas**:

| Hoja | Contenido |
|------|-----------|
| **RESUMEN** | Estadísticas por eje (cuántos con score >= 50, >= 70, promedio top 200) |
| **PERSONALISMO** | Top 200 artículos con mayor score en personalismo |
| **INSTITUCIONALISMO** | Top 200 artículos con mayor score en institucionalismo |
| **POPULISMO** | Top 200 |
| **DOCTRINARISMO** | Top 200 |
| **SOBERANISMO** | Top 200 |
| **GLOBALISMO** | Top 200 |
| **CONSERVADURISMO** | Top 200 |
| **PROGRESISMO** | Top 200 |

## Importante: artículos duplicados

Un artículo puede aparecer en **varias hojas** si tiene scores altos en múltiples ejes. Esto refleja la naturaleza del modelo de regresión multisalida — un artículo NO es "una sola ideología", tiene intensidades simultáneas en 8 dimensiones.

Ejemplo: Un artículo sobre Petro firmando un decreto puede aparecer en:
- Hoja PERSONALISMO (score 75)
- Hoja INSTITUCIONALISMO (score 70)
- Hoja PROGRESISMO (score 60)

## Archivos involucrados

- [scripts/generate_sample.py](../scripts/generate_sample.py) — Genera el Excel

## Comandos

```bash
source .venv/bin/activate

# Generar Excel con top 200 por ideología (default)
python scripts/generate_sample.py

# Cambiar el N (ej: top 100 en vez de 200)
python scripts/generate_sample.py --top 100

# Usar input distinto
python scripts/generate_sample.py --input data/interim/labeled_news_clean.jsonl

# Cambiar nombre de salida
python scripts/generate_sample.py --output muestra_director.xlsx
```

### Parámetros

- `--top N` — Cantidad por ideología (default: 200)
- `--input ARCHIVO` — JSONL etiquetado de entrada
- `--output ARCHIVO` — Excel de salida (default: `muestra_ideologica.xlsx`)

## Recomendación de qué archivo usar como input

| Archivo | Cuándo usar |
|---------|-------------|
| `data/interim/labeled_news.jsonl` | Si NO has corrido el filter (paso 4) |
| `data/interim/labeled_news_clean.jsonl` | ✅ **Recomendado** — después del filter |

## Hoja de RESUMEN

Estadísticas por cada eje:

```
| IDEOLOGIA          | ARTICULOS_>=_50 | ARTICULOS_>=_70 | PROMEDIO_TOP_200 | MIN | MAX |
|-------------------|------------------|-------------------|------------------|-----|-----|
| Personalismo      | 421              | 329               | 78.5             | 70  | 95  |
| Institucionalismo | 788              | 523               | 87.2             | 80  | 95  |
| Populismo         | 150              | 45                | 55.0             | 40  | 90  |
| ...               |                  |                   |                  |     |     |
```

Esto le da al director una visión general de la cobertura del dataset.
