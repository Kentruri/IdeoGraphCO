# 4 — Gold set humano (Handwrite)

Muestreo estratificado de N artículos para anotación humana, en dos formatos:
**Label Studio** (recomendado) y **Excel** (respaldo). El gold set es el
**test set** del modelo (mientras silver es train/val).

**v2 (metodología del anteproyecto):** cada anotador recibe SU bloque, con un
subconjunto de **solape** (los mismos artículos para ambos → Krippendorff α) y
un bloque exclusivo. Se anota **una sola cosa por artículo: la clase
dominante** — la etiqueta categórica que consume el clasificador multiclase.

> Las escalas de intensidad 1-5 por eje son opcionales (`--with-scales`).
> Venían del diseño anterior de regresión sobre 8 ejes; el clasificador
> single-label no las consume, y pedir 9 decisiones por artículo en vez de 1
> multiplica el trabajo sin alimentar al modelo. El α del anteproyecto se
> calcula sobre la clase dominante (nominal), no sobre las escalas.

## De artículos scrapeados a la herramienta, en 3 comandos

```bash
# 1) Muestrear el gold desde el corpus y generar las tareas
python scripts/prepare_gold_set.py --annotators kevin juan --target 700 --overlap 180

# 2) Arrancar Label Studio (déjalo corriendo en su propia terminal)
LABEL_STUDIO_BASE_DATA_DIR=~/label-studio-data \
    ~/label-studio-env/bin/label-studio start --port 8080

# 3) Crear los proyectos e importar los artículos (una sola vez)
python scripts/labelstudio_setup.py --annotators kevin juan \
    --user tu@correo.com --password tu_clave
```

El paso 3 imprime el enlace directo de cada proyecto. Abres
http://localhost:8080, entras al tuyo y anotas: lees el artículo, haces clic
en la clase dominante, `Submit`, siguiente.

## Flags útiles

`prepare_gold_set.py`:

- `--target 700` — cuántos artículos ÚNICOS muestrear (default 200)
- `--overlap 180` — tamaño del bloque compartido para α (default 60)
- `--annotators kevin juan` — nombres (default anotador1 anotador2)
- `--seed 42` — semilla del muestreo
- `--with-scales` — pide además los 8 ejes 1-5 (por defecto NO)

`labelstudio_setup.py`:

- `--replace` — recrea proyectos existentes. **Borra sus anotaciones**
- `--with-scales` — debe coincidir con lo que usaste al preparar
- `--url` — default `http://localhost:8080`

## Output

| Archivo | Contenido |
|---------|-----------|
| `annotation/labelstudio/gold_set_v2_<anotador>_tasks.json` | Tareas de Label Studio por anotador (**sin** `source`/`category`: anotación ciega al medio) |
| `annotation/labelstudio/labeling_config.xml` | Plantilla de la interfaz para pegar en Label Studio |
| `annotation/gold_set_v2_<anotador>.xlsx` | Libro Excel por anotador (respaldo): `clase_dominante` (dropdown, OBLIGATORIA) |
| `annotation/gold_set_v2.jsonl` | Todos los artículos muestreados (texto + meta) |
| `annotation/gold_set_v2_ids.json` | IDs gold — usada por `prepare_splits.py` |
| `annotation/gold_set_v2_assignment.json` | Qué IDs son de solape y cuáles exclusivos de cada uno |

## Flujo de anotación con Label Studio (recomendado)

Cada anotador corre su instancia LOCAL con su propio archivo de tareas — no
hace falta servidor compartido, y la independencia queda garantizada por
construcción.

**Instalación (una vez, cada anotador; NO en el venv del proyecto):**

```bash
pipx install label-studio        # o: python3 -m venv ~/ls && ~/ls/bin/pip install label-studio
label-studio start               # abre http://localhost:8080 (crear cuenta local)
```

**Configurar el proyecto:** lo hace `scripts/labelstudio_setup.py` (paso 3 de
arriba) — crea el proyecto, pega la plantilla e importa las tareas. Si
prefieres hacerlo a mano: `Create Project` → `Labeling Setup` →
`Custom template` → pegar `annotation/labelstudio/labeling_config.xml` →
`Data Import` → subir tu `*_tasks.json`.

**Anotar:** un artículo por pantalla. Lees el texto, haces clic en **la clase
dominante** (obligatoria: Label Studio no deja enviar sin ella) y `Submit`.
Usa el campo de notas cuando dudes — esas notas alimentan la sesión de
consenso. Sesiones de 25-30 artículos; anota SOLO tu proyecto, sin comparar
con el otro anotador hasta terminar.

La interfaz **no muestra el medio ni la categoría** del artículo: el codebook
exige juzgar por el texto, y saber que viene de un medio u otro sesga. El
Excel no puede ocultarlo; Label Studio sí.

**Exportar al terminar:** `Export → JSON` (el formato completo, NO JSON-MIN)
y guardarlo como `annotation/gold_set_v2_<tu_nombre>.json`.

**Ingesta + concordancia** (acepta `.json` de Label Studio y `.xlsx`,
incluso mezclados):

```bash
python scripts/ingest_gold.py --books annotation/gold_set_v2_kevin.json \
    annotation/gold_set_v2_juan.json --audit-silver data/silver/silver_set.jsonl
```

## Flujo alternativo con Excel (respaldo)

1. Cada anotador sube SU libro a Google Drive y anota **sin ver el del otro**
   (el α solo es válido si la anotación del solape es independiente).
2. Al terminar ambos: `File → Download → .xlsx` y reemplazar los locales.
3. La misma ingesta de arriba, pasando los `.xlsx`.

## Después de la ingesta (igual con cualquiera de los dos flujos)

La ingesta:
Calcula **Krippendorff α** (umbral del anteproyecto: ≥ 0.8), audita el
silver contra el consenso humano, y deja las discrepancias en
`annotation/gold_set_v2_discrepancias.csv`.

1. Sesión de consenso: llenar `label_final` en el CSV y re-correr con
   `--consensus annotation/gold_set_v2_discrepancias.csv`.
2. Salida final: `annotation/gold_set_v2_labeled.jsonl` (etiquetas humanas,
   `label_source: human*`) → entra a `prepare_splits.py`.

**Ronda de calibración primero**: antes de anotar el gold completo, anoten
~40 artículos del solape, corran la ingesta y miren el α. Si α < 0.8,
discutan las discrepancias, refinen el codebook y re-anoten ese bloque. Es
mucho más barato descubrirlo con 40 que con 700.

Si α < 0.8: iterar el codebook (eliminar ambigüedades) y re-anotar el solape,
como define el anteproyecto.

## Instalar Label Studio (una vez, cada anotador)

No va en el venv del proyecto: Label Studio instala Django, pandas 3 y numpy 2,
que chocan con las versiones de entrenamiento.

```bash
# necesita Python 3.10+ (el python3 del sistema en macOS suele ser 3.9)
/opt/homebrew/bin/python3.13 -m venv ~/label-studio-env
~/label-studio-env/bin/pip install label-studio
```

La primera vez que abras http://localhost:8080 te pide crear una cuenta
local (correo + contraseña). Esas credenciales son las que pasas a
`labelstudio_setup.py`. Los datos viven en `~/label-studio-data` y sobreviven
al reinicio del servidor.

## Escala humana

Solo la **clase dominante**: una de las 8, la que ESTRUCTURA el argumento del
texto. Si dos empatan, elige la que motivaría el titular y anótalo en `notes`.

Con `--with-scales` se añaden enteros 1-5 por eje como dato secundario de
análisis (no los consume el clasificador).

## Componentes

- [scripts/prepare_gold_set.py](../scripts/prepare_gold_set.py) — muestreo + tareas LS + libros Excel
- [scripts/labelstudio_setup.py](../scripts/labelstudio_setup.py) — crea los proyectos e importa las tareas
- [src/agents/gold/labelstudio.py](../src/agents/gold/labelstudio.py) — plantilla, tareas y parseo del export
- [scripts/ingest_gold.py](../scripts/ingest_gold.py) — ingesta (.json/.xlsx) + α + consenso
- [src/agents/gold/agreement.py](../src/agents/gold/agreement.py) — Krippendorff α (nominal/interval)
