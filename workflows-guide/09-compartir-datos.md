# 9 — Compartir el corpus (Hugging Face)

El corpus pesa 652 MB en disco y 218 MB comprimido: demasiado para git. Vive
en un **repositorio de dataset privado de Hugging Face**, y git guarda solo
`data/corpus.lock` (unos bytes) con la revisión exacta que corresponde a cada
commit del código.

> **Por qué no Google Drive + DVC**, que era el plan inicial: Google bloqueó
> el cliente OAuth por defecto de DVC ("Esta aplicación está bloqueada"), y la
> alternativa —una cuenta de servicio— la prohíbe la política de la
> organización del usuario (`iam.managed.disableServiceAccountKeyCreation`).
> Hugging Face da repos privados gratis, versionados con git-lfs, sin ninguno
> de esos obstáculos.

## Setup (una vez, cada investigador)

1. Cuenta en [huggingface.co](https://huggingface.co).
2. Token de escritura en *Settings → Access Tokens → New token → Write*.
3. Añadirlo a `.env` (ignorado por git):

```bash
echo "HF_TOKEN=hf_..." >> .env
```

Kevin añade a Juan como colaborador en
*huggingface.co/datasets/Kentruri/ideographco-corpus → Settings → Collaborators*.

## Traer el corpus

```bash
.venv/bin/python scripts/dataset_sync.py pull                  # la revisión del lock
.venv/bin/python scripts/dataset_sync.py pull --only-filtered  # solo articles.jsonl (71 MB)
.venv/bin/python scripts/dataset_sync.py pull --latest         # lo más reciente
```

`pull` respeta lo que ya esté en disco; `--force` lo sobrescribe. Descomprime
a un `.part` y renombra al final, así que un corte no deja el corpus a medias.

## Subir cuando el corpus cambie

```bash
.venv/bin/python scripts/dataset_sync.py push -m "corpus tras filtrar el resto"
git add data/corpus.lock && git commit -m "data: corpus actualizado" && git push
```

Ese commit del lock es lo que ancla «este código va con esta versión del
corpus». Sin él, `pull` no sabe qué revisión traer.

## Ver qué hay

```bash
.venv/bin/python scripts/dataset_sync.py status
```

Compara lo que hay en el repo remoto con lo que tienes en disco.

## Nota legal

El corpus contiene texto completo de artículos con derechos de autor. El repo
es **privado** y es para uso académico de los investigadores y el director.
Publicarlo abiertamente es otra cosa: consúltalo con el director. La práctica
habitual en NLP para prensa es distribuir **URLs e IDs**, no el texto — y este
pipeline lo permite, porque con las URLs cualquiera reconstruye el corpus.

## Alternativa rápida (para enseñar unos ejemplos)

```bash
.venv/bin/python scripts/inspect_corpus.py --filtered --category opinion --export muestra.csv
```
