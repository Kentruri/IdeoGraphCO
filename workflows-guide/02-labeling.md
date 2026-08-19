# 2 — Labeling silver (LLM-as-a-Judge, categórico)

Asigna a cada artículo la **clase dominante** (1 de 8, la etiqueta que
consume el clasificador — metodología del anteproyecto) **más** 8 scores de
intensidad continuos en `[0, 1]` como señal secundaria (auditoría/análisis).
No hay campo `is_political`: el dataset ya es 100% político tras la etapa 1.

## Comando

```bash
python scripts/label.py --input data/raw/articles.jsonl
```

## Flags útiles

- `--max-articles 5 --output data/silver/prueba.jsonl --force` — prueba corta
  sobre los primeros 5. **Siempre con `--output` propio**: `--force` abre la
  salida en modo escritura y sin él la prueba TRUNCA `silver_set.jsonl`.
- `--model gemini-2.5-flash-lite` — modelo más barato
- `--output PATH` — escribir a archivo distinto
- `--force` — re-etiquetar desde cero (ignora cursor). **Necesario una vez**
  para migrar el silver legacy (solo scores) al formato categórico.

## Salida por artículo

```json
{"id":"...","text":"...","source":"...",
 "label":"populismo","label_idx":2,"label_source":"silver-llm",
 "judge_model":"gemini-2.5-flash",
 "personalismo":0.78,"institucionalismo":0.23,"populismo":0.61,...}
```

- `label` = clase **dominante** elegida por el juez con criterios de
  desempate del codebook (qué marco estructura el argumento). El
  `response_schema` de Gemini la garantiza como enum de las 8 clases.
- Los 8 scores siguen la escala continua (los 5 niveles del codebook son
  referencias ≈ 0.00/0.25/0.50/0.75/1.00, no anclajes).
- **Legacy**: silver viejo sin `label` se lee vía argmax al vuelo
  (deprecado, con warning por empates) — re-etiquetar con `--force`.

## Componentes

- [scripts/label.py](../scripts/label.py) — CLI
- [src/agents/silver/judge.py](../src/agents/silver/judge.py) — orquestación + retry
- [src/agents/silver/codebook.py](../src/agents/silver/codebook.py) — 8 ejes + reglas + regla de la dominante
