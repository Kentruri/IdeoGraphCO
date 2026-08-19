"""Reconstruye scraper_history.db desde corpus existentes.

La BD de dedup es un cache local que NO viaja con git/DVC: en una máquina
nueva (o si se borra) queda vacía y el scraper re-descargaría todo el corpus.
Este script la reconstruye marcando como "ya scrapeadas" las URLs y hashes de
contenido de los JSONL que ya tienes.

Idempotente: correrlo varias veces no duplica registros (INSERT OR IGNORE).

Además de los artículos CONSERVADOS (raw/silver), restaura las URLs
DESCARTADAS definitivamente por el filtro (desde logs/filter_decisions.jsonl,
si existe): sin ellas, tras un rebuild el scraper re-descargaba y re-filtraba
con API todo lo que ya se había descartado.

Uso:
    python scripts/rebuild_dedup_db.py                          # raw + silver + filter log
    python scripts/rebuild_dedup_db.py --inputs data/raw/articles.jsonl
"""

import argparse
import json
from pathlib import Path

from src.scraper.db import compute_content_hash, get_scraped_count, mark_as_scraped
from src.scraper.urls import normalize_url


def rebuild_from(path: Path) -> int:
    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            url = record.get("url", "")
            text = record.get("text", "")
            if not url or not text:
                continue
            # Se registran AMBAS formas de la URL (cruda y normalizada):
            # el corpus viejo se scrapeó sin normalizar y el pipeline nuevo
            # busca por la normalizada.
            content_hash = compute_content_hash(text)
            scraped_at = record.get("scraped_at") or record.get("date") or ""
            source = record.get("source", "?")
            category = record.get("category", "?")
            for candidate in {url, normalize_url(url)}:
                mark_as_scraped(candidate, content_hash, source, category, str(scraped_at))
            added += 1
    return added


def rebuild_dropped_from_filter_log(path: Path) -> int:
    """Marca las URLs con decisión DEFINITIVA del filtro (kept=False).

    No hay texto completo en el log, así que el hash de contenido queda
    vacío: el dedup por URL es el que evita la re-descarga.
    """
    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("kept") is not False:
                continue
            url = record.get("url", "")
            if not url:
                continue
            for candidate in {url, normalize_url(url)}:
                mark_as_scraped(
                    candidate, "", record.get("source", "?"), "?",
                    str(record.get("ts", "")),
                )
            added += 1
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconstruye la BD de dedup del scraper")
    parser.add_argument(
        "--inputs", nargs="+", default=None,
        help="JSONLs fuente (default: data/raw/articles.jsonl y "
             "data/silver/silver_set.jsonl, los que existan)",
    )
    args = parser.parse_args()

    from src.core.paths import RAW_DIR, SILVER_DIR

    inputs = (
        [Path(p) for p in args.inputs] if args.inputs
        else [RAW_DIR / "articles.jsonl", SILVER_DIR / "silver_set.jsonl"]
    )

    print(f"BD antes: {get_scraped_count()} URLs registradas")
    for path in inputs:
        if not path.exists():
            print(f"  ⊘ {path} no existe, saltando")
            continue
        n = rebuild_from(path)
        print(f"  ✓ {path}: {n} artículos registrados")

    if args.inputs is None:
        from src.core.paths import LOGS_DIR

        filter_log = LOGS_DIR / "filter_decisions.jsonl"
        if filter_log.exists():
            n = rebuild_dropped_from_filter_log(filter_log)
            print(f"  ✓ {filter_log}: {n} descartes definitivos restaurados")
    print(f"BD después: {get_scraped_count()} URLs registradas")


if __name__ == "__main__":
    main()
