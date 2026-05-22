# Data Versioning con DVC

Los datos del proyecto (`data/raw/`, `data/interim/`, `data/processed/`) son grandes y cambian con cada scrape. No los subimos a git — los versiona **DVC** ([dvc.org](https://dvc.org)).

## Cómo funciona

```
┌────────────────────────────────┐
│ git                            │
│  ├─ data/raw.dvc       (hash)  │  ← metadatos (~100 bytes c/u)
│  ├─ data/interim.dvc   (hash)  │
│  └─ data/processed.dvc (hash)  │
└────────────────────────────────┘
              │ los hashes apuntan a:
              ▼
┌────────────────────────────────┐
│ Remote (Google Drive / S3 / …) │
│  └─ archivos reales            │  ← contenido versionado por hash
└────────────────────────────────┘
              │ se descargan al clonar con:
              ▼
┌────────────────────────────────┐
│ data/raw/      (local)         │
│ data/interim/  (local)         │
│ data/processed/(local)         │
└────────────────────────────────┘
```

Cuando hay un cambio (ej. nuevos artículos en `data/raw/`):
1. `dvc add data/raw` → recalcula el hash y actualiza `data/raw.dvc`
2. `git commit data/raw.dvc` → el hash queda versionado
3. `dvc push` → sube el contenido nuevo al remote

Para recuperar en otra máquina:
1. `git clone` → trae el código + los `.dvc`
2. `dvc pull` → trae el contenido real desde el remote

## Setup del remote (configuración inicial)

DVC está inicializado pero **no tiene remote configurado**. Cada máquina necesita acceso al remote para hacer `pull`/`push`.

### Opción A: Google Drive (recomendado para tesis)

15GB gratis. Cómodo si tu compañero también tiene cuenta Google.

```bash
# 1. Instalar soporte (ya instalado)
pip install 'dvc[gdrive]'

# 2. Crear una carpeta en Google Drive llamada "IdeoGraphCO-data"
#    Copia el ID de la URL: drive.google.com/drive/folders/FOLDER_ID_AQUI
#                                                            ^^^^^^^^^^^^

# 3. Configurar como remote por defecto
dvc remote add -d gdrive gdrive://FOLDER_ID_AQUI

# 4. Primera vez: autenticación interactiva en el navegador
dvc push   # abrirá Google login, autoriza DVC
```

### Opción B: S3 / Cloudflare R2

Para producción seria o si la universidad tiene infra. R2 de Cloudflare es gratis hasta 10GB.

```bash
dvc remote add -d myremote s3://bucket-name/path
dvc remote modify myremote endpointurl https://...r2.cloudflarestorage.com
dvc remote modify --local myremote access_key_id YOUR_KEY
dvc remote modify --local myremote secret_access_key YOUR_SECRET
```

### Opción C: Local solamente (sin remote)

Si solo trabajas en una máquina, DVC ya guarda el contenido en `.dvc/cache/` local. No necesitas remote. Pero tu compañero no podrá hacer `pull`.

## Comandos del día a día

```bash
# Después de cambios en data/
dvc add data/raw                  # re-hashear lo que cambió
git add data/raw.dvc              # commitear el nuevo hash
git commit -m "data: scrape v2"
dvc push                          # subir el contenido nuevo al remote

# Al hacer pull desde otra máquina o después de git pull
git pull                          # trae el código + los nuevos .dvc
dvc pull                          # trae el contenido nuevo del remote

# Ver qué archivos están trackeados por DVC
dvc list . data/
dvc status                        # muestra si hay cambios pendientes

# Recuperar una versión anterior
git checkout <commit_hash> data/raw.dvc
dvc checkout                      # restaura los archivos a esa versión
```

## Estado actual

Trackeado por DVC:

| Carpeta | Contenido | Tamaño aprox |
|---------|-----------|--------------|
| `data/raw/` | JSONLs crudos del scraping y post-cleaning | ~10 MB |
| `data/interim/` | JSONLs etiquetados (silver) y backups | ~7 MB |
| `data/processed/` | `splits.json`, tensores futuros | ~10 KB |

No trackeados (regenerable o local):
- `data/scraper_history.db` — SQLite local del scraper
- `**/.label_cursor`, `**/.filter_cursor` — cursors de progreso
- `logs/` — logs de runs
- `*.bak` — backups de scripts

## Para tu compañero (primer setup)

```bash
git clone git@github.com:Kentruri/IdeoGraphCO.git
cd IdeoGraphCO
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# (configurar remote DVC si aún no lo está)
dvc pull   # descarga data/ desde el remote
```
