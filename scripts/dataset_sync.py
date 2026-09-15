"""Sincroniza el corpus con un repositorio privado de Hugging Face.

Por qué no DVC aquí: DVC necesitaba autenticarse contra Google Drive, y esa
vía quedó cerrada dos veces (Google bloqueó el cliente OAuth por defecto de
DVC, y la organización del usuario prohíbe crear claves de cuenta de
servicio). Hugging Face da repos de dataset privados, gratis y versionados
con git-lfs, que es exactamente lo que hace falta.

Qué se versiona y dónde:

- el CONTENIDO del corpus vive en el repo de HF (comprimido, ~68 MB);
- la REVISIÓN concreta que corresponde a este commit de git queda en
  `data/corpus.lock` (unos pocos bytes), que sí se versiona.

Así «este commit del código va con esta versión del corpus» queda anclado,
que era el único motivo real para usar DVC.

Uso:
    python scripts/dataset_sync.py push            # subir lo que hay en disco
    python scripts/dataset_sync.py pull            # traer la revisión del lock
    python scripts/dataset_sync.py pull --latest   # traer lo más reciente
    python scripts/dataset_sync.py status
"""

import argparse
import gzip
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RAW_DIR = ROOT / "data" / "raw"
LOCK_PATH = ROOT / "data" / "corpus.lock"
REPO_ID = "Kentruri/ideographco-corpus"

# Los dos archivos del corpus. El filtrado es el que se usa para entrenar; el
# crudo solo hace falta para volver a filtrar, así que se puede omitir.
FILES = {
    "articles.jsonl": "articles.jsonl.gz",
    "articles_unfiltered.jsonl": "articles_unfiltered.jsonl.gz",
}


def _api():
    import os

    from dotenv import load_dotenv
    from huggingface_hub import HfApi

    load_dotenv(ROOT / ".env")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit(
            "✗ Falta HF_TOKEN.\n"
            "  Crea uno con permiso de escritura en\n"
            "  https://huggingface.co/settings/tokens y añádelo a .env:\n"
            "      HF_TOKEN=hf_..."
        )
    return HfApi(token=token)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compress(src: Path, dest: Path) -> None:
    with open(src, "rb") as fin, gzip.open(dest, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, length=1 << 20)


def count_lines(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def cmd_push(args: argparse.Namespace) -> None:
    api = _api()
    tmp = ROOT / ".hf_upload"
    tmp.mkdir(exist_ok=True)

    manifest = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "files": {}}
    try:
        for name, remote in FILES.items():
            src = RAW_DIR / name
            if not src.exists():
                print(f"  · {name}: no existe, se omite")
                continue
            if args.only_filtered and name != "articles.jsonl":
                print(f"  · {name}: omitido (--only-filtered)")
                continue

            print(f"  comprimiendo {name}…", flush=True)
            gz = tmp / remote
            compress(src, gz)
            n = count_lines(src)
            manifest["files"][remote] = {
                "articles": n,
                "bytes_raw": src.stat().st_size,
                "bytes_gz": gz.stat().st_size,
                "sha256_raw": sha256(src),
            }
            print(f"    {src.stat().st_size/1e6:.0f} MB → {gz.stat().st_size/1e6:.0f} MB"
                  f"  ({n:,} artículos)")

        if not manifest["files"]:
            raise SystemExit("✗ No hay nada que subir.")

        (tmp / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        (tmp / "README.md").write_text(_readme(manifest), encoding="utf-8")

        print(f"\n  subiendo a {REPO_ID}…", flush=True)
        commit = api.upload_folder(
            folder_path=str(tmp), repo_id=REPO_ID, repo_type="dataset",
            commit_message=args.message or "corpus sync",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    revision = getattr(commit, "oid", None) or str(commit)
    LOCK_PATH.write_text(json.dumps({
        "repo_id": REPO_ID, "revision": revision, **manifest,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✓ Subido. Revisión {revision[:12]}")
    print(f"  {LOCK_PATH.relative_to(ROOT)} actualizado — commitéalo:")
    print("    git add data/corpus.lock && git commit -m 'data: corpus actualizado'")


def _readme(manifest: dict) -> str:
    lines = [
        "---", "license: other", "language: [es]",
        "task_categories: [text-classification]", "---", "",
        "# Corpus IdeoGraphCO", "",
        "Noticias políticas colombianas para un clasificador multiclase de",
        "ideología en ocho clases (trabajo de grado, Universidad del Valle).",
        "",
        "**Uso académico entre los investigadores del proyecto y su director.**",
        "Contiene texto completo de artículos con derechos de autor: no",
        "redistribuir. La práctica habitual en NLP para prensa es compartir",
        "URLs e IDs, no el texto.", "",
        "## Archivos", "",
        "| archivo | artículos | tamaño |", "|---|---|---|",
    ]
    for name, meta in manifest["files"].items():
        lines.append(f"| `{name}` | {meta['articles']:,} | "
                     f"{meta['bytes_gz']/1e6:.0f} MB |")
    lines += ["", f"Actualizado: {manifest['updated_at']}", "",
              "## Descargar", "", "```bash",
              "python scripts/dataset_sync.py pull", "```"]
    return "\n".join(lines) + "\n"


def cmd_pull(args: argparse.Namespace) -> None:
    from huggingface_hub import hf_hub_download

    api = _api()
    revision = None
    if not args.latest:
        if not LOCK_PATH.exists():
            raise SystemExit(
                f"✗ No existe {LOCK_PATH.name}. Usa --latest para traer lo "
                "más reciente.")
        revision = json.loads(LOCK_PATH.read_text(encoding="utf-8"))["revision"]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    remotes = [f for f in api.list_repo_files(REPO_ID, repo_type="dataset")
               if f.endswith(".jsonl.gz")]
    if args.only_filtered:
        remotes = [f for f in remotes if f == "articles.jsonl.gz"]

    for remote in remotes:
        local = RAW_DIR / remote[:-3]
        if local.exists() and not args.force:
            print(f"  · {local.name} ya existe, se omite (--force para rehacer)")
            continue
        print(f"  bajando {remote}…", flush=True)
        gz = hf_hub_download(REPO_ID, remote, repo_type="dataset",
                             revision=revision, token=api.token)
        # A un archivo temporal y luego rename: si esto se corta, el corpus
        # bueno no queda a medias.
        tmp = local.with_suffix(local.suffix + ".part")
        with gzip.open(gz, "rb") as fin, open(tmp, "wb") as fout:
            shutil.copyfileobj(fin, fout, length=1 << 20)
        tmp.replace(local)
        print(f"    → {local.relative_to(ROOT)}  ({count_lines(local):,} artículos)")

    print("\n✓ Corpus listo en data/raw/")


def cmd_status(args: argparse.Namespace) -> None:
    print(f"repo      : {REPO_ID} (privado)")
    if LOCK_PATH.exists():
        lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        print(f"revisión  : {lock['revision'][:12]}  ({lock['updated_at']})")
        for name, meta in lock["files"].items():
            print(f"  {name:32} {meta['articles']:>8,} art.  "
                  f"{meta['bytes_gz']/1e6:>5.0f} MB")
    else:
        print("revisión  : (sin corpus.lock: nunca se ha subido)")

    print("\nen disco:")
    for name in FILES:
        p = RAW_DIR / name
        if p.exists():
            print(f"  {name:32} {count_lines(p):>8,} art.  "
                  f"{p.stat().st_size/1e6:>5.0f} MB")
        else:
            print(f"  {name:32} (no está)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sincroniza el corpus con Hugging Face (repo privado)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_push = sub.add_parser("push", help="Subir el corpus de disco a HF")
    p_push.add_argument("--message", "-m", type=str, default=None)
    p_push.add_argument("--only-filtered", action="store_true",
                        help="Solo articles.jsonl (omite el crudo, 421 MB)")
    p_push.set_defaults(func=cmd_push)

    p_pull = sub.add_parser("pull", help="Traer el corpus desde HF")
    p_pull.add_argument("--latest", action="store_true",
                        help="La revisión más reciente, no la del lock")
    p_pull.add_argument("--only-filtered", action="store_true")
    p_pull.add_argument("--force", action="store_true",
                        help="Sobrescribir lo que ya esté en disco")
    p_pull.set_defaults(func=cmd_pull)

    p_status = sub.add_parser("status", help="Qué hay aquí y qué hay allá")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
