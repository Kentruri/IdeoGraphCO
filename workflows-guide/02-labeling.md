# 2 — Labeling silver (LLM-as-a-Judge)

Asigna a cada artículo 8 scores ideológicos **continuos en `[0, 1]`** usando
Gemini con el codebook como system prompt. No hay campo `is_political`: el
dataset ya es 100% político tras la etapa 1.

## Comando

```bash
python scripts/label.py --input data/raw/articles.jsonl
```

## Flags útiles

- `--max-articles 5 --force` — prueba corta sobre los primeros 5
- `--model gemini-2.5-flash-lite` — modelo más barato
- `--output PATH` — escribir a archivo distinto
- `--force` — re-etiquetar desde cero (ignora cursor)

## Escala

- LLM da floats directos en `[0, 1]` (ej. `0.42`, `0.07`, `0.83`).
- Los 5 niveles del codebook (Ausente / Leve / Moderado / Marcado / Dominante)
  son referencias semánticas aproximadas (≈ 0.00, 0.25, 0.50, 0.75, 1.00),
  no anclajes obligatorios.
- `response_schema` de Gemini garantiza valores en `[0, 1]` y los 8 campos.

## Output

`data/silver/silver_set.jsonl` — una línea por artículo:

```json
{"id":"...","text":"...","source":"...",
 "personalismo":0.78,"institucionalismo":0.23,"populismo":0.61,...}
```

## Componentes

- [scripts/label.py](../scripts/label.py) — CLI
- [src/agents/silver/judge.py](../src/agents/silver/judge.py) — orquestación + retry
- [src/agents/silver/codebook.py](../src/agents/silver/codebook.py) — 8 ejes + reglas
