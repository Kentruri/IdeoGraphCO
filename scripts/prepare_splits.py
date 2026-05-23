"""Pre-computa los splits train/val/test y los guarda a disco.

Diseño:
- **test** = los artículos del gold set humano (anotación manual). Estos NUNCA
  se mezclan con train/val. Sus IDs se leen de `annotation/gold_set_v1_ids.json`.
- **train/val** = el resto del corpus (silver labels del LLM), dividido
  aleatoriamente con semilla determinista.

Por qué hacerlo en archivo separado:
- Si mañana scrapeas más artículos y los añades al JSONL etiquetado, los
  índices de un random_split cambian aunque uses la misma semilla.
- Pre-computar a disco "congela" el split a los artículos que tengas hoy.
- El test = gold siempre es el mismo, sin importar cuánto crezca el corpus.

Uso:
    python scripts/prepare_splits.py
    python scripts/prepare_splits.py --val-ratio 0.15 --seed 42
    python scripts/prepare_splits.py --gold-ids annotation/gold_set_v1_ids.json
    python scripts/prepare_splits.py --no-gold   # split tradicional sin gold
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
        help="JSONL etiquetado (default: data/interim/labeled_news.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Archivo de splits (default: data/processed/splits.json)",
    )
    parser.add_argument(
        "--gold-ids", type=str, default=None,
        help="JSON con IDs del gold set (default: annotation/gold_set_v1_ids.json). "
             "Si existe, esos artículos forman el test set; el resto se divide train/val.",
    )
    parser.add_argument(
        "--no-gold", action="store_true",
        help="No usar gold set: hace split tradicional train/val/test al azar.",
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.15,
        help="Fracción de los NO-gold que va a val (default: 0.15 ≈ 15%%).",
    )
    parser.add_argument(
        "--test-ratio-fallback", type=float, default=0.15,
        help="Solo en modo --no-gold: fracción que va a test (default: 0.15).",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    from src.core.paths import INTERIM_DIR, PROCESSED_DIR, ROOT

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news.jsonl"
    if not input_path.exists():
        logger.error("No existe %s. Corre el labeling primero.", input_path)
        return

    output_path = Path(args.output) if args.output else PROCESSED_DIR / "splits.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Cargar el corpus con sus IDs
    articles: list[dict] = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                articles.append(json.loads(line))
    total = len(articles)
    if total == 0:
        logger.error("El JSONL está vacío.")
        return

    # Cargar IDs gold (si aplica)
    gold_ids: set[str] = set()
    if not args.no_gold:
        gold_path = (
            Path(args.gold_ids) if args.gold_ids
            else ROOT / "annotation" / "gold_set_v1_ids.json"
        )
        if gold_path.exists():
            with open(gold_path, encoding="utf-8") as f:
                gold_ids = set(json.load(f))
            logger.info("Gold set: %d IDs cargados desde %s", len(gold_ids), gold_path)
        else:
            logger.warning(
                "No existe %s — split tradicional sin gold set.", gold_path,
            )

    # Separar índices gold vs no-gold por `id`
    gold_indices: list[int] = []
    nongold_indices: list[int] = []
    articles_sin_id = 0
    for i, a in enumerate(articles):
        aid = a.get("id")
        if not aid:
            articles_sin_id += 1
        if aid and aid in gold_ids:
            gold_indices.append(i)
        else:
            nongold_indices.append(i)

    if articles_sin_id > 0:
        logger.warning(
            "%d artículos sin campo `id`. Esto debería pasarte solo con datos "
            "de scrapes muy viejos; rescatae con `dvc pull` o re-scrapea con "
            "el pipeline actual (que añade `id` desde el origen).",
            articles_sin_id,
        )

    # Diagnóstico: gold IDs que no aparecen en el JSONL etiquetado
    found_gold = {articles[i].get("id") for i in gold_indices}
    missing_gold = gold_ids - found_gold
    if missing_gold:
        logger.warning(
            "%d IDs del gold set NO están en el JSONL etiquetado (probablemente "
            "fallaron en el labeling). Esos no irán a test.",
            len(missing_gold),
        )

    # Mezcla determinista de los NO-gold
    rng = random.Random(args.seed)
    rng.shuffle(nongold_indices)

    if args.no_gold or not gold_indices:
        # Split tradicional sin gold
        test_size = int(len(nongold_indices) * args.test_ratio_fallback)
        val_size = int(len(nongold_indices) * args.val_ratio)
        train_size = len(nongold_indices) - val_size - test_size
        train_ids = sorted(nongold_indices[:train_size])
        val_ids = sorted(nongold_indices[train_size:train_size + val_size])
        test_ids = sorted(nongold_indices[train_size + val_size:])
        gold_used = False
    else:
        # Split con gold: test = gold, train/val = no-gold
        val_size = int(len(nongold_indices) * args.val_ratio)
        train_size = len(nongold_indices) - val_size
        train_ids = sorted(nongold_indices[:train_size])
        val_ids = sorted(nongold_indices[train_size:])
        test_ids = sorted(gold_indices)
        gold_used = True

    splits = {
        "source_file": str(input_path),
        "total_samples": total,
        "seed": args.seed,
        "val_ratio": args.val_ratio,
        "gold_used": gold_used,
        "gold_ids_file": str(gold_path) if not args.no_gold and gold_ids else None,
        "train": train_ids,
        "val": val_ids,
        "test": test_ids,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)

    pct = lambda n: f"{100*n/total:.1f}%"
    print()
    print("=" * 60)
    print("  SPLITS GENERADOS")
    print(f"  Fuente:        {input_path}")
    print(f"  Total:         {total} artículos")
    print(f"  Gold-aware:    {'SÍ (test = gold humano)' if gold_used else 'NO (split aleatorio)'}")
    print(f"  Train:         {len(train_ids):4d}  ({pct(len(train_ids))})")
    print(f"  Val:           {len(val_ids):4d}  ({pct(len(val_ids))})")
    print(f"  Test:          {len(test_ids):4d}  ({pct(len(test_ids))})")
    if gold_used and missing_gold:
        print(f"  ⚠ Gold faltantes en JSONL: {len(missing_gold)}")
    print(f"  Semilla:       {args.seed}")
    print(f"  Salida:        {output_path}")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
