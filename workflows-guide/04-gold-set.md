# 4 — Gold set humano

Muestreo estratificado de N artículos y exporta a Excel para anotación humana.
El gold set es el **test set** del modelo (mientras silver es train/val).

## Comando

```bash
python scripts/prepare_gold_set.py
```

## Flags útiles

- `--target 200` — cuántos artículos muestrear (default 200)
- `--seed 42` — semilla del muestreo
- `--output annotation/gold_v2.xlsx` — path del Excel

## Output

| Archivo | Contenido |
|---------|-----------|
| `annotation/gold_set_v1.xlsx` | Excel con instrucciones + 8 columnas por eje (validación: enteros 1-5) |
| `annotation/gold_set_v1.jsonl` | Mismos artículos en JSONL (texto + meta) |
| `annotation/gold_set_v1_ids.json` | Lista de IDs gold — usada por `prepare_splits.py` |

## Flujo de anotación

1. Sube `gold_set_v1.xlsx` a Google Drive → abrir como Google Sheets
2. Compartir con tu compañero como Editor
3. Cada uno anota su mitad (validación de datos solo permite 1-5)
4. Al terminar, `File → Download → .xlsx` y reemplaza el local

## Escala humana

Enteros 1-5 (cómoda para humanos). Mapeo al modelo:

```
1 (Ausente) → 0.00     3 (Moderado)  → 0.50     5 (Dominante) → 1.00
2 (Leve)    → 0.25     4 (Marcado)   → 0.75
```

## Componente

- [scripts/prepare_gold_set.py](../scripts/prepare_gold_set.py) — muestreo + Excel
