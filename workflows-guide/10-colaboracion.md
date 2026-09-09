# 10 — Trabajar a dos: código, corpus y anotaciones sincronizados

Tres cosas distintas viajan por tres canales distintos, porque tienen tamaños
y ritmos distintos:

| Qué | Tamaño | Canal | Por qué |
|-----|--------|-------|---------|
| Código, guías, codebook | KB | **git** (GitHub) | cambia a diario, se revisa, se hace `blame` |
| Corpus (`data/raw/*.jsonl`) | 630 MB | **DVC → Google Drive** | git no aguanta binarios grandes; DVC guarda en git solo un hash |
| Anotaciones del gold | pocos MB | **git** (`annotation/`) | son el resultado del trabajo humano: deben quedar versionadas y auditables |

## El principio que manda: independencia

El anteproyecto exige que los dos investigadores anoten el bloque de solape
**de forma independiente** y que sobre él se calcule Krippendorff α ≥ 0,8.
Ese α solo vale si ninguno vio la etiqueta del otro antes de poner la suya.

Por eso el diseño **no** es "una pantalla donde los dos ven lo que va marcando
el otro". Es:

- cada uno anota **su** proyecto en **su** Label Studio local;
- los dos pueden ver en cualquier momento **cuánto** lleva el otro (progreso);
- las **etiquetas** del otro se ven solo cuando ambos terminaron el solape, en
  la sesión de consenso — que es justo el paso que el protocolo prevé.

Un servidor compartido de Label Studio con los dos dentro daría sincronía en
tiempo real, pero mataría el α. No compensa.

## Puesta en marcha (una vez)

### Quien ya tiene el corpus (Kevin)

```bash
# 1. Versionar el código. NUNCA `git add .` mientras data/ no esté ignorado.
git add scripts src tests workflows-guide .claude .gitignore CLAUDE.md requirements.txt
git commit -m "feat: filtrado con agente, servicio launchd y guías"
git push

# 2. Remoto DVC en Google Drive: crear la carpeta IdeoGraphCO-data en Drive,
#    copiar el ID de su URL y compartirla con el otro investigador (editor).
.venv/bin/dvc remote add -d gdrive gdrive://PEGA_EL_ID_AQUI
git add .dvc/config && git commit -m "chore: remoto DVC en Drive"

# 3. Congelar y subir el corpus (dvc add escribe data/raw en .gitignore solo)
.venv/bin/dvc add data/raw
.venv/bin/dvc push                       # la 1ª vez abre el navegador para autorizar
git add data/raw.dvc data/.gitignore
git commit -m "data: corpus filtrado 41k + crudo" && git push

# 4. Muestrear el gold y generar las tareas de los dos anotadores
.venv/bin/python scripts/prepare_gold_set.py --annotators kevin juan --target 1200 --overlap 300
git add annotation/ && git commit -m "gold: muestra v2 y tareas por anotador" && git push
```

Decisión sep-2026: **1.200 artículos gold, 300 de solape** → 750 por persona
(~12-18 h cada uno). Con 8 clases son ~150 por clase: intervalos de ±8 pp,
suficientes para que las diferencias entre encoders del OE2 sean detectables.

`prepare_gold_set.py` deja en `annotation/gold_set_v2_assignment.json` qué
IDs son de solape y cuáles exclusivos de cada uno: es lo que después usa
`ingest_gold.py` para calcular el α sobre el bloque correcto.

### El otro investigador

```bash
git clone git@github.com:Kentruri/IdeoGraphCO.git && cd IdeoGraphCO
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/dvc pull                       # trae el corpus desde Drive

# Label Studio va en SU propio entorno, no en el venv del proyecto
python3 -m venv ~/label-studio-env && ~/label-studio-env/bin/pip install label-studio
```

### Los dos: cargar el proyecto en Label Studio

```bash
# terminal 1 — el servidor, se deja corriendo
LABEL_STUDIO_BASE_DATA_DIR=~/label-studio-data ~/label-studio-env/bin/label-studio start --port 8080
# → http://localhost:8080, crear cuenta local

# terminal 2 — crear el proyecto e importar las tareas propias
.venv/bin/python scripts/labelstudio_setup.py --annotators kevin juan --user tu@correo --password tu_clave
```

Cada uno anota **solo el proyecto con su nombre**. La interfaz oculta la
fuente del artículo a propósito.

## El ciclo de trabajo (cada sesión)

```bash
# antes de empezar
git pull

# anotar en Label Studio; al terminar la sesión: Export → JSON (completo, no JSON-MIN)
# guardarlo como annotation/gold_set_v2_<tu_nombre>.json  (sobrescribe el anterior)

# publicar
git add annotation/gold_set_v2_<tu_nombre>.json
git commit -m "gold: <tu_nombre> +N artículos"
git push
```

**Ver el progreso de los dos** (funciona aunque uno no haya terminado):

```bash
.venv/bin/python scripts/ingest_gold.py --books annotation/gold_set_v2_kevin.json annotation/gold_set_v2_juan.json
```

Reporta cuántos artículos anotó cada uno, cuántos del solape tienen ya dos
etiquetas y el α **provisional** sobre esos. No mira las etiquetas del otro
por ti: solo el número.

## Ronda de calibración antes del gold completo

Anoten primero **~40 artículos del solape**, exporten, y corran la ingesta.

- α ≥ 0,8 → sigan con todo.
- α < 0,8 → siéntense con `annotation/gold_set_v2_discrepancias.csv`,
  afinen el codebook y re-anoten ese bloque. Descubrirlo con 40 cuesta una
  tarde; con 700, semanas.

## Sesión de consenso (al terminar el solape)

```bash
.venv/bin/python scripts/ingest_gold.py --books annotation/gold_set_v2_kevin.json annotation/gold_set_v2_juan.json
# → annotation/gold_set_v2_discrepancias.csv : una fila por desacuerdo

# los dos juntos llenan la columna label_final, y luego:
.venv/bin/python scripts/ingest_gold.py --books ... --consensus annotation/gold_set_v2_discrepancias.csv
git add annotation/ && git commit -m "gold: consenso v2" && git push
```

Salida: `annotation/gold_set_v2_labeled.jsonl` con `label_source: human*`,
que es lo que entra a `prepare_splits.py` como conjunto de prueba.

## Cuando el corpus cambie (por ejemplo, al terminar el scraping)

```bash
.venv/bin/dvc add data/raw && .venv/bin/dvc push
git add data/raw.dvc && git commit -m "data: corpus 54k" && git push
# el otro:  git pull && .venv/bin/dvc pull
```

El gold ya muestreado **no se vuelve a muestrear**: sus IDs están en
`annotation/gold_set_v2_ids.json` y `prepare_splits.py` los excluye del
entrenamiento aunque el corpus crezca.

## Lo que no hay que hacer

- **`git add .`** antes de que `dvc add data/raw` haya escrito el `.gitignore`.
  Son 630 MB y GitHub los rechaza (o peor, los acepta y el repo queda inservible).
- **Enseñarse las etiquetas** del solape antes de que los dos hayan terminado.
  Invalida el α y, con él, el producto P1.3.
- **Anotar el proyecto del otro** en Label Studio. Cada nombre, su proyecto.
- **Subir `logs/`**: está ignorado, y así debe seguir — `filter_decisions.jsonl`
  pesa 207 MB.

## Comandos de diagnóstico

```bash
git status --short                 # ¿qué tengo sin publicar?
.venv/bin/dvc status -c             # ¿hay corpus local sin subir a Drive?
.venv/bin/dvc data status           # ¿cambió data/ desde el último add?
```

Ver también [09-compartir-datos.md](09-compartir-datos.md) (detalle de DVC) y
[04-gold-set.md](04-gold-set.md) (la anotación en sí).
