# 9 — Compartir los datos (DVC + Google Drive)

El corpus pesa ~180 MB, demasiado para git. DVC guarda en git solo un archivo
de hashes (`data/raw.dvc`, ~100 bytes) y el contenido real va a Google Drive.

## Setup (una sola vez, quien configura)

```bash
# 1. Crear una carpeta en Google Drive llamada "IdeoGraphCO-data".
#    Copiar su ID de la URL:
#    drive.google.com/drive/folders/1a2B3cD4eF5gH6iJ    ← esto
```

```bash
# 2. Registrar el remoto y commitearlo
.venv/bin/dvc remote add -d gdrive gdrive://PEGA_EL_ID_AQUI
git add .dvc/config && git commit -m "chore: remoto DVC en Drive"
```

```bash
# 3. Compartir la carpeta de Drive con el otro investigador (permiso de editor)
```

La primera vez que corras `dvc push` se abre el navegador para autorizar la
cuenta de Google. El token queda guardado localmente.

## Subir datos (cuando el corpus cambia)

```bash
.venv/bin/dvc add data/raw          # calcula hashes → crea/actualiza data/raw.dvc
.venv/bin/dvc push                  # sube el contenido a Drive
git add data/raw.dvc .gitignore
git commit -m "data: corpus 49k artículos"
git push
```

Igual para `data/silver` y `data/processed` cuando existan.

## Bajar datos (el otro investigador, o una máquina nueva)

```bash
git clone <repo> && cd IdeoGraphCO
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # incluye dvc y dvc-gdrive
dvc pull                            # trae el contenido real desde Drive
```

Después, cada vez que quiera actualizarse:

```bash
git pull      # trae los .dvc actualizados
dvc pull      # trae el contenido nuevo
```

## Comandos de diagnóstico

```bash
dvc status -c          # ¿hay algo local sin subir al remoto?
dvc remote list        # ¿qué remoto está configurado?
dvc data status        # ¿cambió algo en data/ desde el último add?
```

## Alternativa rápida (sin DVC)

Para mostrar unos ejemplos al director, no montes nada:

```bash
# muestra en CSV, abrible en Excel
.venv/bin/python scripts/inspect_corpus.py --category opinion --export muestra.csv

# el corpus entero comprimido (~40 MB: el JSONL comprime muy bien)
gzip -c data/raw/articles_unfiltered.jsonl > corpus.jsonl.gz
```

## Nota legal

El corpus contiene el texto completo de artículos con derechos de autor.
Compartirlo entre los investigadores y el director para uso académico está
bien. **Publicarlo abiertamente** (GitHub, HuggingFace) es otra cosa:
consúltalo con el director. La práctica habitual en NLP para prensa es
distribuir las **URLs e IDs**, no el texto — y este pipeline lo permite,
porque con las URLs y `scripts/scraper.py` cualquiera reconstruye el corpus.

Ver también [docs/data-versioning.md](../docs/data-versioning.md) para el
detalle de cómo funciona DVC y qué carpetas versiona.
