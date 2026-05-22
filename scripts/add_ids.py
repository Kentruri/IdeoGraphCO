"""Migra JSONLs existentes para añadirles un campo `id` estable.

El ID se calcula desde el URL con sha256(url)[:16]. Idempotente: si el
artículo ya tiene id, no lo sobrescribe (a menos que pases --overwrite).

Uso:
    python scripts/add_ids.py                    # migra los 4 archivos default
    python scripts/add_ids.py --files data/raw/news.jsonl
    python scripts/add_ids.py --overwrite        # recalcula incluso si ya hay id
"""

import argparse
import json
import shutil
from pathlib import Path

from src.core.ids import article_id


DEFAULT_FILES = [
    "data/raw/news.jsonl",
    "data/raw/news_clean.jsonl",
    "data/raw/news_filtered.jsonl",
    "annotation/gold_set_v1.jsonl",
]


def migrate_file(path: Path, overwrite: bool = False) -> tuple[int, int]:
    """Añade `id` a cada línea. Retorna (total, añadidos)."""
    if not path.exists():
        print(f"  ⊘ no existe: {path}")
        return 0, 0

    backup = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup)

    total = 0
    added = 0
    out_lines: list[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            d = json.loads(line)
            if "id" not in d or overwrite:
                url = d.get("url", "")
                if not url:
                    out_lines.append(json.dumps(d, ensure_ascii=False))
                    continue
                d = {"id": article_id(url), **d}  # id primero por convención
                added += 1
            out_lines.append(json.dumps(d, ensure_ascii=False))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")

    print(f"  ✓ {path}  ({total} líneas, {added} IDs añadidos)  backup: {backup.name}")
    return total, added


def main() -> None:
    parser = argparse.ArgumentParser(description="Añade IDs estables a JSONLs")
    parser.add_argument(
        "--files", nargs="+", default=DEFAULT_FILES,
        help=f"Archivos a migrar (default: {len(DEFAULT_FILES)} predeterminados)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Recalcula el id incluso si ya existe",
    )
    args = parser.parse_args()

    print("Migración de IDs (sha256(url)[:16]):\n")
    total_files = 0
    total_added = 0
    for fp in args.files:
        path = Path(fp)
        n, a = migrate_file(path, overwrite=args.overwrite)
        if n > 0:
            total_files += 1
            total_added += a

    print(f"\n✓ {total_files} archivos procesados, {total_added} IDs añadidos en total")
    print("  Los .bak son backups; bórralos cuando confirmes que todo está bien.")


if __name__ == "__main__":
    main()
