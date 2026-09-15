# 10 — Trabajar a dos: código, corpus y anotaciones sincronizados

Tres cosas distintas viajan por tres canales distintos, porque tienen tamaños
y ritmos distintos:

| Qué | Tamaño | Canal | Por qué |
|-----|--------|-------|---------|
| Código, guías, codebook | KB | **git** (GitHub) | cambia a diario, se revisa, se hace `blame` |
| Corpus (`data/raw/*.jsonl`) | 218 MB comprimido | **Hugging Face** (repo privado) | git no aguanta binarios grandes; en git solo va `data/corpus.lock` con la revisión |
| Anotaciones del gold | pocos MB | **Label Studio compartido** (+ export a `annotation/` al cerrar el solape y al final) | una sola base de datos, sincronía inmediata, sin ceremonia de exportar/subir en cada sesión |

## El principio que manda: independencia

El anteproyecto exige que los dos investigadores anoten el bloque de solape
**de forma independiente** y que sobre él se calcule Krippendorff α ≥ 0,8.
Ese α solo vale si ninguno vio la etiqueta del otro antes de poner la suya.

Por eso el diseño **no** es "una pantalla donde los dos ven lo que va marcando
el otro". Es:

- **un solo Label Studio para los dos**, corriendo en el Mac de Kevin (que ya
  está encendido 24/7 para el scraping), al que Juan entra por una URL pública (túnel de Cloudflare);
- cada uno anota **su** proyecto (`Gold set — kevin`, `Gold set — juan`); el
  bloque común está en ambos;
- los dos ven en cualquier momento **cuánto** lleva el otro (la portada muestra
  el avance de cada proyecto); las **etiquetas** del otro se miran solo cuando
  ambos terminaron el solape, en la sesión de consenso.

Label Studio (edición gratuita) no impide abrir el proyecto del otro: la
independencia del α depende de **no hacerlo**. Es una regla de trabajo, no un
candado.

## Puesta en marcha (una vez)

### Quien ya tiene el corpus (Kevin)

```bash
# 1. Versionar el código. NUNCA `git add .` mientras data/ no esté ignorado.
git add scripts src tests workflows-guide .claude .gitignore CLAUDE.md requirements.txt
git commit -m "feat: filtrado con agente, servicio launchd y guías"
git push

# 2. Corpus en Hugging Face — YA HECHO (Kentruri/ideographco-corpus, privado).
#    Cada investigador pone su propio token en .env; ver 09-compartir-datos.md.

# 3. Subir el corpus y anclar su revisión
.venv/bin/python scripts/dataset_sync.py push -m "corpus v1"
git add data/corpus.lock
git add data/raw.dvc data/.gitignore
git commit -m "data: corpus filtrado 41k + crudo" && git push

# 4. Muestrear el gold y generar las tareas — YA HECHO (commit c6de08b)
.venv/bin/python scripts/prepare_gold_set.py --annotators kevin juan --target 1200 --overlap 300

# 5. Label Studio como servicio permanente + proyectos de los dos
./scripts/labelstudio_service.sh install --public-url http://<mac-de-kevin>:8080 && ./scripts/labelstudio_service.sh start
.venv/bin/python scripts/labelstudio_setup.py --annotators kevin juan --replace --user kevin@cloudnonic.com --password '...'

# 6. Túnel público para que Juan llegue al servidor (sin cuenta ni admin)
brew install cloudflared
./scripts/tunnel_service.sh install && ./scripts/tunnel_service.sh start
./scripts/tunnel_service.sh url      # imprime la URL y el enlace de invitación
```

**La URL cambia en cada arranque del túnel.** Es el precio de no usar cuenta
de Cloudflare. Tras un reinicio del Mac, `./scripts/tunnel_service.sh url`
da la nueva y hay que pasársela a Juan; el servicio reconfigura Label Studio
solo (sin `LABEL_STUDIO_HOST` correcto, Django rechaza los formularios por
CSRF y las invitaciones apuntan a localhost).

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
echo "HF_TOKEN=hf_..." >> .env        # su propio token de Hugging Face
.venv/bin/python scripts/dataset_sync.py pull --only-filtered

```

Para **anotar**, Juan no necesita el corpus, ni Label Studio, ni instalar
nada: solo un navegador. El `dvc pull` es para cuando toque entrenar.

1. Abrir el enlace de invitación que le pasa Kevin
   (`https://….trycloudflare.com/user/signup/?token=…`) y crear su usuario
   (correo + contraseña, viven solo en ese servidor).
2. Entrar y abrir el proyecto **Gold set — juan**.

Requisito: el Mac de Kevin encendido, con Label Studio y el túnel arriba. Si
Juan ve "no se puede conectar", es eso.

### Un solo servidor, dos proyectos

Los proyectos los crea Kevin una vez con `labelstudio_setup.py` (arriba, paso
5) en el servidor compartido. Juan no carga nada: entra y su proyecto ya está.
La interfaz oculta la fuente del artículo a propósito, y en cada archivo de
tareas **las 300 del bloque común van primero**: anotar en orden es empezar
por el solape.

## El ciclo de trabajo (cada sesión)

Entrar a la URL del túnel, abrir **tu** proyecto, anotar. Nada
más: la base de datos es una y está en el Mac de Kevin, así que lo que anota
uno lo ve el otro (como avance) al instante.

**Ver el progreso de los dos**: la portada de Label Studio muestra, por
proyecto, cuántas tareas están completadas. Ese número es público para ambos;
las etiquetas no se miran.

**Requisito**: el Mac de Kevin encendido, con Label Studio y el túnel
arriba (`./scripts/labelstudio_service.sh status` y
`./scripts/tunnel_service.sh status`).

**Copia de seguridad**: al cerrar el bloque de solape y al terminar, Kevin
exporta cada proyecto (`Export → JSON`, el completo) a
`annotation/gold_set_v2_<nombre>.json` y lo sube a git. Es lo que consume
`ingest_gold.py` y lo que queda versionado para el informe.

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
.venv/bin/python scripts/dataset_sync.py push -m "corpus 54k"
git add data/corpus.lock && git commit -m "data: corpus 54k" && git push
# el otro:  git pull && .venv/bin/python scripts/dataset_sync.py pull
```

El gold ya muestreado **no se vuelve a muestrear**: sus IDs están en
`annotation/gold_set_v2_ids.json` y `prepare_splits.py` los excluye del
entrenamiento aunque el corpus crezca.

## Lo que no hay que hacer

- **`git add .`** a lo bruto: `data/raw/` está ignorado, pero son 652 MB y
  un `git add -f` los metería en el repo y lo dejaría inservible.
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
