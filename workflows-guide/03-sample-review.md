# 3 — Revisión de muestra (opcional)

Genera un Excel con los top N artículos por cada eje ideológico, ordenados
por score descendente. Útil para que el director (o tú) revise visualmente
si las labels del silver son consistentes con el contenido.

## Comando

```bash
python scripts/generate_sample.py
```

## Flags útiles

- `--top 200` — cuántos artículos por eje (default 200)
- `--output muestra.xlsx` — path del Excel
- `--input PATH` — JSONL alternativo

## Output

Excel con 9 hojas:

| Hoja | Contenido |
|------|-----------|
| `RESUMEN` | Estadísticas por eje (media, cuántos con score ≥ 0.5, ≥ 0.7) |
| `PERSONALISMO`, `INSTITUCIONALISMO`, ... | Top N artículos por cada eje (8 hojas) |

## Cuándo usarlo

- Después del labeling (etapa 2) para validar calidad antes de entrenar.
- Para revisión por parte del director / asesor de tesis.
- Para detectar ejes donde el LLM da scores extraños (todo en 0, o todo en 1).
