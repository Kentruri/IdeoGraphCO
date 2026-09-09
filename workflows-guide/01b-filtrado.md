# 1b — Filtrar el corpus (quién decide qué entra)

Tras `collect_corpus.py --no-filter` quedan **50.351 artículos sin filtrar**
en `data/raw/articles_unfiltered.jsonl`. El filtro decide cuáles son política
**colombiana** y entran a `data/raw/articles.jsonl`.

Hay tres motores posibles y se combinan.

| Motor | Cómo se invoca | Coste | Volumen razonable |
|-------|----------------|-------|-------------------|
| Gemini (API) | `filter_corpus.py --provider gemini` | créditos de API | los 50.351 |
| Claude por API | `--provider claude` (necesita `ANTHROPIC_API_KEY`) | créditos aparte | los 50.351 |
| **El agente de Claude Code** | `scripts/agent_filter.py` | ninguno | **cientos, no decenas de miles** |

## El tamaño real de la tarea

Leer los 50.351 artículos en la sesión cuesta **~15,9 millones de tokens solo
de texto** (medido: 1.263 caracteres de media por artículo con el recorte a
1.200). Son ~16 ventanas de contexto llenas, sin contar instrucciones ni respuestas:
**~840 lotes de 60 artículos**. No se hace en una sesión ni en cinco. Por eso
todo el diseño gira en torno a reanudar sin perder ni repetir nada, y por eso
conviene mirar `status` antes de cada tanda.

## El agente `filtro-politico` — la travesía completa

Decisión de ago-2026: **el agente filtra todo el corpus**; Gemini solo
desempata los casos donde el agente queda genuinamente indeciso.

```
Skill(skill="codebook-filtro")          ← el criterio, fuente única
Agent(subagent_type="filtro-politico")  ← el proceso
```

El ciclo, por lote:

```bash
.venv/bin/python scripts/agent_filter.py next --reset-session   # 1ª vez de la sesión
# … el agente lee data/agent_batches/lote_NNN.txt y escribe las decisiones …
.venv/bin/python scripts/agent_filter.py ingest --batch N --decisions data/agent_batches/decisiones_NNN.txt
.venv/bin/python scripts/agent_filter.py next                   # siguientes
.venv/bin/python scripts/agent_filter.py status                 # progreso
```

**Reanudable de verdad.** El cursor (`data/agent_batches/filter_state.json`)
es un número de línea del corpus y **solo avanza al ingerir**: si la sesión se
corta a mitad de lote, esos artículos vuelven a salir en vez de perderse. Un
lote entregado y sin ingerir bloquea el siguiente `next`, para que ningún
hueco pase inadvertido.

**El corte por presupuesto** es el equivalente medible del "95 % del
contexto". Un agente no puede leer su propio porcentaje de contexto, así que
el script lleva la cuenta exacta de los tokens de artículo que le ha
entregado y corta **antes** de darle el lote que lo desbordaría:

```
⏹  PRESUPUESTO DE LA TANDA AGOTADO — para aquí.
   Cursor: línea 12,480 de 50,351
   Para retomar:  python scripts/agent_filter.py next --reset-session
```

Por defecto 120.000 tokens de texto por tanda (`--budget` lo cambia).

**El desempate.** Cuando el agente escribe `dud` en vez de una categoría,
`ingest` manda **solo ese artículo** a Gemini (`gemini-2.5-flash`, el bueno:
para tan pocos casos el coste es irrelevante) y registra la decisión con
`engine: gemini-desempate`. Si Gemini no responde, el artículo se queda sin
decidir y reaparece en un lote futuro — no se inventa una categoría.

## Desatendido: el servicio de launchd

Igual que `collector.sh` con el scraping, pero para el filtrado. `caffeinate`
impide que el equipo se duerma y el trabajo sobrevive al cierre de la
terminal.

```bash
./scripts/filter_service.sh install --model opus   # o sonnet
./scripts/filter_service.sh start
./scripts/filter_service.sh status                 # progreso + estado
./scripts/filter_service.sh logs                   # en vivo
./scripts/filter_service.sh stop                   # pausar
```

**Cómo funciona.** El agente vive dentro de una sesión de Claude Code, así que
no puede ser un proceso de launchd. Lo que sí lo es: `claude -p`, que corre una
sesión headless y termina. `filter_runner.sh` lo invoca tanda tras tanda; el
cursor persistente hace que cada invocación continúe donde acabó la anterior.

Sin TTY, un diálogo de permisos colgaría el servicio para siempre, así que las
herramientas van explícitamente acotadas: `Bash(*agent_filter.py*)`, `Read`,
`Write`, `Skill`.

**Cuándo se detiene solo:**

| Situación | Reacción |
|-----------|----------|
| Corpus terminado | materializa el archivo final y sale con éxito |
| **Semanal ≥ 80 %** | deja de consumir y espera a que renueve la semana (suelta `caffeinate`: el Mac puede dormir) |
| **Límite de uso** | espera hasta la renovación: la hora que anuncie el aviso, o **4,5 h** si no la dice |
| Sobrecarga pasajera (529, timeouts) | espera 5 min |
| Una tanda supera 90 min | la mata; ese lote se rehace |
| 3 tandas seguidas sin avanzar | **para** — seguir solo quemaría cuota |
| 6 esperas seguidas por cuota (~27 h) | **para** |

Distinguir el límite de uso de una sobrecarga pasajera importa en las dos
direcciones: reintentar cada 5 min contra una ventana de 5 h son decenas de
intentos que no adelantan nada, y esperar 5 h por un 529 tira media jornada.

**La puerta semanal** se comprueba ANTES de cada tanda con
`claude -p "/usage"`, que se resuelve en el cliente y cuesta 0 tokens. Lee la
línea `Current week (all models): N% used` — no la de sesión, que aparece
justo antes y también dice "% used". Si `/usage` resulta ilegible, el
servicio sigue trabajando y lo registra: un fallo de lectura no debe parar
días de trabajo.

```bash
./scripts/filter_service.sh install --weekly-stop 80   # el valor por defecto
```

## El archivo único: `data/raw/articles.jsonl`

Hay dos artefactos y conviene no confundirlos:

| Archivo | Qué es | Cómo se escribe |
|---------|--------|-----------------|
| `logs/filter_decisions.jsonl` | **toda** decisión (conservar y descartar) con motor, confianza, razón y `text_head` | solo vía `ingest`, append-only |
| `data/raw/articles.jsonl` | el **corpus filtrado**: un artículo por línea, solo los conservados | `agent_filter.py build`, reconstruido entero |

El servicio corre `build` **tras cada tanda**, así que el archivo único va
creciendo sobre la marcha; no hay que esperar a que termine todo para mirarlo
o para entrenar el prefilter con lo que ya hay.

`build` reescribe el archivo completo cada vez, de forma atómica (a un `.tmp`
que se renombra al final). Es idempotente: correrlo dos veces da lo mismo, y
una decisión corregida se refleja sin dejar dentro el artículo viejo. Con
`--prefer-engine claude-agent` (el valor por defecto) el agente manda sobre
cualquier otra decisión que exista para el mismo artículo.

```bash
.venv/bin/python scripts/agent_filter.py build          # manual, cuando quieras
.venv/bin/python scripts/inspect_corpus.py --filtered   # mirar lo que hay
```

## Calibración: permisivo en politicidad, estricto en colombianidad

El codebook (`FILTER_SYSTEM_PROMPT`, regla de oro 7) invirtió su desempate en
ago-2026: ante duda entre político y no-político **entra**. La razón es que
la opinión política es el material más valioso del corpus — el encuadre
ideológico está explícito en vez de implícito — y el desempate anterior la
estaba tumbando. Entran también el debate de política sectorial (educación,
salud, pensiones, ambiente), la memoria histórica con lectura política y los
reclamos de respuesta estatal.

El eje de colombianidad **no se relajó**: ahí la duda sigue resolviéndose
como `political_foreign`, porque las ocho clases están ancladas en actores de
Colombia y un texto de política extranjera es inetiquetable con ellas.

## Alternativa: el agente enseña, el modelo local trabaja

```bash
# 1. Sacar una muestra estratificada por fuente
.venv/bin/python scripts/agent_filter.py export --limit 400

# 2. Pedirle al agente en la sesión que lea data/agent_batches/lote_00N.txt
#    y escriba una línea por artículo:  «n categoría [confianza] [marcas]»
#      pol=political_article  for=political_foreign  non=nonpolitical_article
#      bio=biography_static   gar=garbage
#      marcas: br=boilerplate  dg=digest  tr=truncado  pw=paywall

# 3. Volcar sus decisiones al log
.venv/bin/python scripts/agent_filter.py ingest --batch 1 --decisions decisiones.txt

# 4. Repetir hasta ~2.000 decisiones y entrenar el prefilter local
.venv/bin/python scripts/train_prefilter.py

# 5. El prefilter resuelve gratis lo obvio; el LLM solo ve la zona gris
.venv/bin/python scripts/filter_corpus.py --prefilter --prefer-engine claude-agent
```

Es el mismo patrón teacher→student que ya documenta `src/scraper/prefilter.py`,
con el agente como maestro.

## Relevo automático entre proveedores

```bash
.venv/bin/python scripts/filter_corpus.py --provider gemini,claude
```

Cuando Gemini agota créditos, Claude toma el relevo **sin perder el artículo
en curso ni reiniciar el proceso**, y el ritmo entre llamadas se ajusta al
proveedor nuevo (Gemini free tier espera 4,5 s; Claude, 0,2 s). Requiere
`ANTHROPIC_API_KEY` en `.env` y `pip install anthropic`.

Nada se paga dos veces: `filter_corpus.py` reutiliza toda decisión que ya esté
en `logs/filter_decisions.jsonl`, la haya tomado quien la haya tomado.

## Antes de mezclar motores: medir si son intercambiables

```bash
# muestrear artículos que Gemini YA decidió, para que el agente los repita
.venv/bin/python scripts/agent_filter.py export --overlap-with llm --limit 200
# … el agente decide, se ingiere, y luego:
.venv/bin/python scripts/agent_filter.py compare --a claude-agent --b llm
```

Devuelve **Krippendorff α** entre los dos motores sobre los artículos que
ambos vieron, más la tabla de desacuerdos por par de categorías.

> **Resultado preliminar (n = 12, solo demostrativo):** α = 0,52 en la
> decisión binaria conservar/descartar; 75 % de acuerdo simple. Gemini
> conservó 7 de 12, el agente 4 de 12: **Gemini es más permisivo**. Los
> desacuerdos se concentran donde cabía esperarlos (una carta de opinión
> sobre política educativa, una crónica de desastre natural, una crónica
> histórica sindical, un caso judicial ordinario). Con n = 12 el intervalo de
> confianza es enorme y **no sustenta ninguna conclusión**: hace falta
> repetirlo con ~200 antes de citar cifra alguna.

Si α < 0,8, filtrar el corpus a medias entre ambos motores mezcla dos
fronteras de decisión distintas y la composición del corpus deja de ser
homogénea. Opciones: usar **un solo motor** para todo el corpus, o declarar
con `--prefer-engine` cuál manda cuando ambos decidieron lo mismo — y
documentar la elección, porque afecta a qué entra al dataset.

## Qué queda registrado

`logs/filter_decisions.jsonl`, una línea por decisión, con `engine`
(`llm` / `prefilter` / `claude-agent`), `provider` (`gemini` / `claude`),
`category`, `confidence`, `reason`, `text_issues` y `text_head`. Es a la vez
el dataset de entrenamiento del prefilter y la trazabilidad de qué criterio
formó el corpus.
