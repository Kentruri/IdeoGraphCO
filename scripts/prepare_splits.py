"""Pre-computa los splits train/val/test y los guarda a disco.

Garantiza que TODOS los modelos del benchmark usen exactamente los mismos
índices, incluso si se añaden nuevas muestras al JSONL en el futuro.

Por qué hacerlo en archivo separado:
- Si mañana scrapeas 50 artículos más y los añades a labeled_news_clean.jsonl,
  los índices de un random_split cambian aunque uses la misma semilla.
- Pre-computar a disco "congela" el split a 1145 muestras (o las que tengas hoy).
- Para una nueva corrida con más datos, generas un nuevo splits.json
  (ej: splits_v2.json) sin tocar el anterior.

Uso:
    python scripts/prepare_splits.py
    python scripts/prepare_splits.py --output data/processed/splits.json
    python scripts/prepare_splits.py --val-split 0.15 --test-split 0.15 --seed 42
"""

import argparse
import json
import logging
import random
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-computa splits train/val/test")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL etiquetado (default: data/interim/labeled_news_clean.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Archivo de splits (default: data/processed/splits.json)",
    )
    parser.add_argument("--val-split", type=float, default=0.15)
    parser.add_argument("--test-split", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from src.paths import INTERIM_DIR, PROCESSED_DIR

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news_clean.jsonl"
    if not input_path.exists():
        # Fallback al archivo sin filtrar si no existe el filtrado
        fallback = INTERIM_DIR / "labeled_news.jsonl"
        if fallback.exists():
            logger.warning(
                "No existe %s, usando %s en su lugar", input_path, fallback,
            )
            input_path = fallback
        else:
            logger.error("No existe ningún JSONL etiquetado. Corre el labeling primero.")
            return

    output_path = Path(args.output) if args.output else PROCESSED_DIR / "splits.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Contar líneas del JSONL
    with open(input_path, encoding="utf-8") as f:
        total = sum(1 for line in f if line.strip())

    test_size = int(total * args.test_split)
    val_size = int(total * args.val_split)
    train_size = total - val_size - test_size

    # Mezcla determinista
    indices = list(range(total))
    rng = random.Random(args.seed)
    rng.shuffle(indices)

    train_ids = sorted(indices[:train_size])
    val_ids = sorted(indices[train_size:train_size + val_size])
    test_ids = sorted(indices[train_size + val_size:])

    splits = {
        "source_file": str(input_path),
        "total_samples": total,
        "seed": args.seed,
        "val_split": args.val_split,
        "test_split": args.test_split,
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)

    print()
    print("=" * 60)
    print("  SPLITS GENERADOS")
    print(f"  Fuente: {input_path}")
    print(f"  Total muestras: {total}")
    print(f"  Train: {len(train_ids)} ({len(train_ids)*100/total:.1f}%)")
    print(f"  Val:   {len(val_ids)} ({len(val_ids)*100/total:.1f}%)")
    print(f"  Test:  {len(test_ids)} ({len(test_ids)*100/total:.1f}%)")
    print(f"  Semilla: {args.seed}")
    print(f"  Salida: {output_path}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
