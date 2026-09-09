# 9 — Compartir los datos (DVC + Google Drive)

El corpus pesa ~180 MB, demasiado para git. DVC guarda en git solo un archivo
de hashes (`data/raw.dvc`, ~100 bytes) y el contenido real va a Google Drive.

## Setup (una sola vez)

Google **bloqueó el cliente OAuth por defecto de DVC** (sep-2026: "Esta
aplicación está bloqueada"), así que la autorización por navegador ya no
sirve. Se usa una **cuenta de servicio**: una identidad de Google Cloud con
su propia clave JSON, sin navegador, sin caducidad, igual para los dos.

**Quien configura (Kevin), en https://console.cloud.google.com:**

1. Selector de proyecto (arriba) → *Nuevo proyecto* → nombre `IdeoGraphCO`.
2. *APIs y servicios → Biblioteca* → buscar **Google Drive API** → *Habilitar*.
3. *APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio*
   → nombre `dvc-ideographco` → *Crear y continuar* → sin rol → *Listo*.
4. Clic en la cuenta creada → pestaña *Claves* → *Agregar clave → Crear clave
   nueva → JSON*. Se descarga un `.json`: **es la llave del corpus, no va a
   git ni a un chat público**.
5. Copiar el correo de la cuenta (`dvc-ideographco@ideographco-….iam.gserviceaccount.com`)
   y en Drive **compartir la carpeta `IdeoGraphCO-dataset` con ese correo como
   Editor**. Sin este paso la cuenta no ve la carpeta.

**Cada investigador, en su máquina** (la clave la comparte Kevin por un canal
privado, nunca por el repo):

```bash
mkdir -p ~/.config/ideographco && mv ~/Downloads/ideographco-*.json ~/.config/ideographco/gdrive-sa.json
.venv/bin/dvc remote modify --local gdrive gdrive_service_account_json_file_path "$HOME/.config/ideographco/gdrive-sa.json"
```

`--local` escribe en `.dvc/config.local`, que está ignorado por git: la ruta
(y la clave) se quedan en tu máquina. El modo cuenta-de-servicio ya viene en
`.dvc/config` para los dos.

Los archivos subidos quedan a nombre de la cuenta de servicio (cuota propia
de 15 GB, sobra): no borres el proyecto de Google Cloud mientras el corpus
viva ahí.

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
