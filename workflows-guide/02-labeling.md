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

## Ensemble de jueces (recomendado para el silver definitivo)

Varios LLM de **familias distintas** ven el mismo artículo y una regla de
consenso decide. Todo vive en `src/agents/silver/`:

| módulo | qué hace |
|---|---|
| `judges.py` | catálogo de jueces (`gemini`, `gemini-lite`, `claude`, `claude-sonnet`) y el prompt (codebook propio o externo) |
| `consensus.py` | la regla: `unanimous` o `majority`. **El desacuerdo no se descarta**: se conserva la etiqueta mayoritaria con `status` y `agreement`, y `accepted` dice si pasa la regla |
| `ensemble.py` | recorre el corpus, excluye el gold, escribe el silver y `*.verdicts.jsonl` (lo que dijo cada juez: la trazabilidad) |
| `calibration.py` | contra el gold humano: precisión por juez, α entre jueces, y si el acuerdo **predice** el acierto |

### Por qué no descartar el desacuerdo

Quitar los artículos donde los jueces discrepan elimina los casos difíciles.
El silver queda más fácil que la realidad y que el gold (que no tiene ese
filtro): el modelo parece mejor en validación de lo que es en test, y las
clases ambiguas se vacían. Por eso el silver lleva `consensus.status` y
`consensus.agreement` en cada registro: quien entrena filtra por `accepted`
o pondera por `agreement`, pero la decisión queda explícita y reversible.

### Por qué familias distintas

Dos copias del mismo modelo se equivocan igual y coinciden también cuando
fallan. Su acuerdo mide consistencia, no corrección. `build_judges` avisa si
todos los jueces son de la misma familia.

### El agente de Claude Code como juez (sin API key)

Igual que en el filtrado: el agente lee lotes, escribe una clase por artículo
y sus votos se acumulan junto a los de Gemini.

```bash
.venv/bin/python scripts/silver_agent.py next --reset-session   # 1ª vez de la sesión
# …el agente lee data/silver/agent_batches/lote_NNN.txt y escribe las decisiones…
.venv/bin/python scripts/silver_agent.py ingest --batch N --decisions <archivo>
.venv/bin/python scripts/silver_agent.py next                   # siguientes
```

Con `Skill(skill="codebook-silver")` y `Agent(subagent_type="juez-silver")`.

**Los votos se acumulan, el consenso se deriva.** Ese es el cambio que permite
usar al agente: va por lotes dentro de una sesión, mientras Gemini recorre el
corpus de corrido. Exigir que voten a la vez lo dejaba fuera. Ahora los dos
escriben en `data/silver/verdicts.jsonl` (una línea por voto) y el silver sale
del cruce:

```bash
.venv/bin/python scripts/silver_ensemble.py --judges gemini --max-articles 12000
.venv/bin/python scripts/silver_agent.py build --rule majority
.venv/bin/python scripts/silver_agent.py status
```

`build` no gasta ninguna llamada: relee los votos guardados. Así se puede
probar otra regla, o añadir un tercer juez meses después, sin re-preguntar a
los que ya votaron.

Si un juez vota dos veces el mismo artículo gana el voto **más reciente**, y
sigue contando una sola vez — un voto viejo y uno nuevo del mismo juez no
pueden formar "mayoría" entre ellos.

### Orden de trabajo

```bash
# 0. (cuando exista) el codebook del anotador como prompt
#    --codebook docs/codebook_juan.md   ← se le añade el bloque de formato JSON solo

# 1. Calibrar sobre el gold YA ANOTADO (unas 600 llamadas, no 24.000)
python scripts/silver_calibrate.py run --judges gemini,claude --sample 300
python scripts/silver_calibrate.py report --rule majority
python scripts/silver_calibrate.py report --rule unanimous     # gratis: sin LLM

# 2. Con la regla justificada por el report, el silver de verdad
python scripts/silver_ensemble.py --judges gemini,claude --rule majority --max-articles 12000
```

El report dice `P(correcto | unánime)` frente a `P(correcto | discrepancia)`.
Si la brecha es grande, la regla filtra errores; si es pequeña, solo filtra
dificultad y conviene `majority` con ponderación en vez de descartar.

El juez `claude` necesita `ANTHROPIC_API_KEY` en `.env` y
`pip install anthropic`. Sin él, `gemini,gemini-lite` funciona pero es la
misma familia: el aviso saldrá, y con razón.

### Registro silver del ensemble

Además de los campos del juez simple:

```json
"label_source": "silver-ensemble",
"judge_models": ["gemini-2.5-flash", "claude-haiku-4-5-20251001"],
"consensus": {"label": "populismo", "status": "unanime", "accepted": true,
              "agreement": 1.0, "votes": {"populismo": 2}, "n_judges": 2, "n_valid": 2}
```

`status` ∈ `unanime · mayoria · discrepancia · unico · sin_veredicto`. Los
`sin_veredicto` no entran al silver (van a `.failed`); los `discrepancia` con
empate tampoco tienen etiqueta y solo quedan en `verdicts.jsonl`.

## Componentes

- [scripts/label.py](../scripts/label.py) — CLI
- [src/agents/silver/judge.py](../src/agents/silver/judge.py) — orquestación + retry
- [src/agents/silver/codebook.py](../src/agents/silver/codebook.py) — 8 ejes + reglas + regla de la dominante
