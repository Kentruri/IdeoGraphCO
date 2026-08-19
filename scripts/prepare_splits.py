"""Construye el dataset canónico y los splits train/val/test (por ID).

Diseño v2 (corrige los hallazgos de la revisión):
- **Splits por ID, no por índice**: si el JSONL crece o se reordena, los
  índices posicionales apuntaban a artículos equivocados sin error.
- **El test lleva etiquetas HUMANAS**: se fusiona `gold_set_*_labeled.jsonl`
  (salida de scripts/ingest_gold.py) sobre el silver. Sin ese archivo, el
  script se niega a marcar el test como "gold humano" (antes evaluaba
  contra las etiquetas del mismo LLM que etiquetó el train — circular).
- **Estratificación por clase** en train/val (con el desbalance real del
  corpus, un val sin estratificar hace ruidoso el f1_macro de selección).
- **Guardia anti-fuga**: artículos de train/val con el mismo hash de
  contenido o mismo título normalizado que un artículo de test (cables
  republicados) se excluyen.

Salidas:
- data/processed/dataset.jsonl — corpus canónico (silver + gold humano fusionado)
- data/processed/splits.json   — {"version": 2, "id_based": true, ...}

Uso:
    python scripts/prepare_splits.py --gold-labeled annotation/gold_set_v2_labeled.jsonl
    python scripts/prepare_splits.py --val-ratio 0.15 --seed 42
    python scripts/prepare_splits.py --allow-silver-test   # SOLO desarrollo
"""

import argparse
import hashlib
import json
import logging
import random
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def normalize_title(title: str) -> str:
    decomposed = unicodedata.normalize("NFD", title.lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(stripped.split())


def content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Dataset canónico + splits por ID")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL silver (default: data/silver/silver_set.jsonl)",
    )
    parser.add_argument(
        "--gold-labeled", type=str, default=None,
        help="JSONL del gold humano (salida de ingest_gold.py). "
             "Default: annotation/gold_set_v2_labeled.jsonl si existe.",
    )
    parser.add_argument(
        "--dataset-output", type=str, default=None,
        help="Dataset canónico (default: data/processed/dataset.jsonl)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Archivo de splits (default: data/processed/splits.json)",
    )
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--allow-silver-test", action="store_true",
        help="Permite un test con etiquetas SILVER (sin gold humano). "
             "SOLO para desarrollo: las métricas resultantes son circulares "
             "(el test comparte el mismo LLM etiquetador que el train) y NO "
             "sirven para el reporte de la tesis.",
    )
    args = parser.parse_args()

    from src.core.paths import PROCESSED_DIR, ROOT, SILVER_DIR
    from src.core.schema import IDEOLOGY_CLASSES
    from src.training.data.dataset import resolve_label_idx

    input_path = Path(args.input) if args.input else SILVER_DIR / "silver_set.jsonl"
    if not input_path.exists():
        logger.error("No existe %s. Corre el labeling primero.", input_path)
        return

    gold_labeled_path = (
        Path(args.gold_labeled) if args.gold_labeled
        else ROOT / "annotation" / "gold_set_v2_labeled.jsonl"
    )
    dataset_path = (
        Path(args.dataset_output) if args.dataset_output
        else PROCESSED_DIR / "dataset.jsonl"
    )
    output_path = Path(args.output) if args.output else PROCESSED_DIR / "splits.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Cargar silver ---
    silver = load_jsonl(input_path)
    by_id: dict[str, dict] = {}
    for record in silver:
        aid = record.get("id")
        if not aid:
            logger.warning("Registro sin `id` descartado (title=%r)", record.get("title", "")[:60])
            continue
        record.setdefault("label_source", "silver-llm")
        by_id[aid] = record

    # --- Fusionar gold humano ---
    gold_ids: set[str] = set()
    if gold_labeled_path.exists():
        gold = load_jsonl(gold_labeled_path)
        for record in gold:
            aid = record["id"]
            gold_ids.add(aid)
            # El gold pisa al silver: misma noticia, etiqueta humana.
            by_id[aid] = record
        logger.info(
            "Gold humano: %d artículos fusionados desde %s", len(gold_ids), gold_labeled_path,
        )
    elif args.allow_silver_test:
        legacy_ids_path = ROOT / "annotation" / "gold_set_v1_ids.json"
        if legacy_ids_path.exists():
            with open(legacy_ids_path, encoding="utf-8") as f:
                gold_ids = set(json.load(f)) & set(by_id)
        logger.warning(
            "=" * 70 + "\n"
            "  MODO DESARROLLO: el test usará etiquetas SILVER (LLM), no humanas.\n"
            "  Las métricas de test resultantes son CIRCULARES y no sirven para\n"
            "  el reporte de la tesis (OE3). Corre scripts/ingest_gold.py cuando\n"
            "  la anotación esté lista.\n" + "=" * 70
        )
    else:
        logger.error(
            "No existe %s.\n"
            "El test de la tesis debe llevar etiquetas HUMANAS (anteproyecto, "
            "Calibración Humana). Corre scripts/ingest_gold.py primero, o usa "
            "--allow-silver-test explícitamente para un split de desarrollo.",
            gold_labeled_path,
        )
        return

    # --- Validar etiquetas y particionar ---
    test_ids: list[str] = []
    pool_by_class: dict[int, list[str]] = defaultdict(list)
    invalid = 0
    for aid, record in by_id.items():
        try:
            label_idx = resolve_label_idx(record)
        except ValueError as e:
            logger.warning("Etiqueta inválida en %s: %s", aid, e)
            invalid += 1
            continue
        if aid in gold_ids:
            test_ids.append(aid)
        else:
            pool_by_class[label_idx].append(aid)

    # --- Guardia anti-fuga: near-duplicados del test fuera de train/val ---
    test_hashes = {content_hash(by_id[aid].get("text", "")) for aid in test_ids}
    test_titles = {
        normalize_title(by_id[aid].get("title", ""))
        for aid in test_ids if by_id[aid].get("title")
    }
    leaked = 0
    for label_idx, ids in pool_by_class.items():
        kept = []
        for aid in ids:
            record = by_id[aid]
            is_dup = (
                content_hash(record.get("text", "")) in test_hashes
                or (record.get("title") and normalize_title(record["title"]) in test_titles)
            )
            if is_dup:
                leaked += 1
            else:
                kept.append(aid)
        pool_by_class[label_idx] = kept
    if leaked:
        logger.info(
            "Anti-fuga: %d near-duplicados del test excluidos de train/val", leaked,
        )

    # --- Dedup DENTRO del pool train/val ---
    # Los cables republicados (Colprensa/EFE, comunicados que FCM/Asocapitales
    # y las alcaldías duplican) entran con URLs distintas; sin este paso el
    # mismo texto cae en train Y val e infla las métricas de validación.
    seen_hashes: set[str] = set()
    seen_titles: set[str] = set()
    internal_dups = 0
    for label_idx in sorted(pool_by_class):
        kept = []
        for aid in sorted(pool_by_class[label_idx]):
            record = by_id[aid]
            h = content_hash(record.get("text", ""))
            t = (
                normalize_title(record["title"])
                if record.get("title") else None
            )
            if h in seen_hashes or (t and t in seen_titles):
                internal_dups += 1
                continue
            seen_hashes.add(h)
            if t:
                seen_titles.add(t)
            kept.append(aid)
        pool_by_class[label_idx] = kept
    if internal_dups:
        logger.info(
            "Dedup interno train/val: %d duplicados de contenido/título excluidos",
            internal_dups,
        )

    # --- Split estratificado train/val por clase ---
    rng = random.Random(args.seed)
    train_ids: list[str] = []
    val_ids: list[str] = []
    for label_idx in sorted(pool_by_class):
        ids = sorted(pool_by_class[label_idx])
        rng.shuffle(ids)
        n_val = round(len(ids) * args.val_ratio)
        # Nunca vaciar el train de una clase por redondeo
        n_val = min(n_val, max(0, len(ids) - 1))
        val_ids.extend(ids[:n_val])
        train_ids.extend(ids[n_val:])
    rng.shuffle(train_ids)
    rng.shuffle(val_ids)

    # --- Escribir dataset canónico + splits ---
    keep_ids = set(train_ids) | set(val_ids) | set(test_ids)
    with open(dataset_path, "w", encoding="utf-8") as f:
        for aid, record in by_id.items():
            if aid in keep_ids:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    test_label_source = "human" if gold_labeled_path.exists() else "silver"
    splits = {
        "version": 2,
        "id_based": True,
        "dataset_file": str(dataset_path),
        "source_file": str(input_path),
        "gold_labeled_file": str(gold_labeled_path) if gold_labeled_path.exists() else None,
        "test_label_source": test_label_source,
        "seed": args.seed,
        "val_ratio": args.val_ratio,
        "stratified": True,
        "leaked_excluded": leaked,
        "train": sorted(train_ids),
        "val": sorted(val_ids),
        "test": sorted(test_ids),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)

    # --- Resumen con distribución por clase (visibiliza el colapso de clases) ---
    def class_distribution(ids: list[str]) -> Counter:
        return Counter(resolve_label_idx(by_id[aid]) for aid in ids)

    total = len(keep_ids)
    pct = lambda n: f"{100 * n / total:.1f}%"  # noqa: E731
    print()
    print("=" * 72)
    print("  SPLITS GENERADOS (v2, por ID)")
    print(f"  Dataset:      {dataset_path}  ({total} artículos)")
    print(f"  Test labels:  {test_label_source.upper()}"
          + ("  ⚠ SOLO DESARROLLO" if test_label_source == "silver" else " (gold humano)"))
    print(f"  Train: {len(train_ids):4d} ({pct(len(train_ids))})   "
          f"Val: {len(val_ids):4d} ({pct(len(val_ids))})   "
          f"Test: {len(test_ids):4d} ({pct(len(test_ids))})")
    if invalid:
        print(f"  ⚠ {invalid} artículos con etiqueta inválida excluidos")
    print()
    print(f"  {'Clase':<18} {'train':>6} {'val':>5} {'test':>5}")
    train_dist = class_distribution(train_ids)
    val_dist = class_distribution(val_ids)
    test_dist = class_distribution(test_ids) if test_ids else Counter()
    for idx, cls in enumerate(IDEOLOGY_CLASSES):
        print(f"  {cls:<18} {train_dist.get(idx, 0):>6} "
              f"{val_dist.get(idx, 0):>5} {test_dist.get(idx, 0):>5}")
    empty = [IDEOLOGY_CLASSES[i] for i in range(len(IDEOLOGY_CLASSES))
             if train_dist.get(i, 0) == 0]
    if empty:
        print(f"\n  ⚠ Clases SIN ejemplos de train: {', '.join(empty)}")
        print("    El F1-macro se degrada con clases vacías — considerar scrapear")
        print("    fuentes que las cubran o revisar el etiquetado.")
    print(f"\n  Semilla: {args.seed}   Salida: {output_path}")
    print("=" * 72)
    print()


if __name__ == "__main__":
    main()
