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
  contenido o mismo título normalizado que un artículo de test o del gold
  reservado completo (`gold_set_v2.jsonl`, anotado o no) se excluyen (cables
  republicados). Así train/val no cambian cuando termina la anotación.
- **Validación agrupada por medio** (`--group-by-source`): ningún medio cae a
  la vez en train y val. Los boletines de un mismo medio son casi idénticos
  y el dedup solo atrapa los exactos; sin agrupar, el val premia al modelo
  que memoriza la plantilla del medio en vez de la ideología.
- **Subconjunto de cribado** (`--train-subset N`): un train reducido y
  estratificado con el MISMO val, para comparar encoders rápido.

Salidas:
- data/processed/dataset.jsonl — corpus canónico (silver + gold humano fusionado)
- data/processed/splits.json   — {"version": 2, "id_based": true, ...}

Uso:
    python scripts/prepare_splits.py --gold-labeled annotation/gold_set_v2_labeled.jsonl
    python scripts/prepare_splits.py --val-ratio 0.15 --seed 42
    python scripts/prepare_splits.py --allow-silver-test   # SOLO desarrollo
    python scripts/prepare_splits.py --allow-silver-test --group-by-source \\
        --train-subset 5000 --subset-output data/processed/splits_cribado.json
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


def load_reserved_gold(annotation_dir: Path) -> tuple[set[str], list[dict]]:
    """IDs y textos de TODO el gold reservado, esté o no anotado.

    La guardia anti-fuga comparaba train/val solo con el test ya armado. En
    modo desarrollo ese test sale vacío (el silver excluye el gold, así que
    `gold_ids & by_id` no encuentra nada) y con el gold a medio anotar solo
    cubría la parte anotada: los casi-duplicados del resto entraban a
    train/val, y los splits cambiaban al terminar la anotación. Leer la
    muestra completa fija train/val desde ya.
    """
    for ids_name, sample_name in (("gold_set_v2_ids.json", "gold_set_v2.jsonl"),
                                  ("gold_set_v1_ids.json", "gold_set_v1.jsonl")):
        ids_path = annotation_dir / ids_name
        if not ids_path.exists():
            continue
        data = json.loads(ids_path.read_text(encoding="utf-8"))
        ids = set(data if isinstance(data, list) else data.get("ids", []))
        sample_path = annotation_dir / sample_name
        records = (
            [r for r in load_jsonl(sample_path) if r.get("id") in ids]
            if sample_path.exists() else []
        )
        return ids, records
    return set(), []


def exclude_leaks(pool_by_class: dict[int, list[str]], by_id: dict[str, dict],
                  guard_records: list[dict]) -> int:
    """Saca de train/val lo que comparte hash de contenido o título normalizado
    con `guard_records` (cables republicados). Devuelve cuántos sacó."""
    hashes = {content_hash(r.get("text", "")) for r in guard_records}
    titles = {normalize_title(r["title"]) for r in guard_records if r.get("title")}
    leaked = 0
    for label_idx, ids in pool_by_class.items():
        kept = []
        for aid in ids:
            record = by_id[aid]
            is_dup = (
                content_hash(record.get("text", "")) in hashes
                or (record.get("title") and normalize_title(record["title"]) in titles)
            )
            if is_dup:
                leaked += 1
            else:
                kept.append(aid)
        pool_by_class[label_idx] = kept
    return leaked


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
    parser.add_argument(
        "--group-by-source", action="store_true",
        help="Val agrupado por medio (`source`): ningún medio en train y val a la vez.",
    )
    parser.add_argument(
        "--train-subset", type=int, default=None,
        help="Escribe además un split con N artículos de train (estratificado, "
             "mismo val) en --subset-output.",
    )
    parser.add_argument(
        "--subset-output", type=str, default=None,
        help="Archivo del split reducido (default: data/processed/splits_cribado.json)",
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
        # Se busca primero el gold VIGENTE (v2). Antes solo se miraba el v1,
        # así que con un gold v2 muestreado el test se armaba con artículos
        # que NO eran los reservados, y los 1.301 del gold podían acabar en
        # entrenamiento.
        for ids_path in (ROOT / "annotation" / "gold_set_v2_ids.json",
                         ROOT / "annotation" / "gold_set_v1_ids.json"):
            if not ids_path.exists():
                continue
            with open(ids_path, encoding="utf-8") as f:
                data = json.load(f)
            ids = data if isinstance(data, list) else data.get("ids", [])
            gold_ids = set(ids) & set(by_id)
            logger.info("IDs del gold reservados desde %s: %d",
                        ids_path.name, len(gold_ids))
            break
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

    # --- Gold reservado completo (anotado o no): nunca va a train/val ---
    reserved_ids, reserved_records = load_reserved_gold(ROOT / "annotation")
    logger.info("Gold reservado: %d IDs, %d con texto para la guardia anti-fuga",
                len(reserved_ids), len(reserved_records))

    # --- Validar etiquetas y particionar ---
    test_ids: list[str] = []
    pool_by_class: dict[int, list[str]] = defaultdict(list)
    invalid = 0
    reserved_excluded = 0
    for aid, record in by_id.items():
        try:
            label_idx = resolve_label_idx(record)
        except ValueError as e:
            logger.warning("Etiqueta inválida en %s: %s", aid, e)
            invalid += 1
            continue
        if aid in gold_ids:
            test_ids.append(aid)
        elif aid in reserved_ids:
            # Gold reservado que aún no tiene etiqueta humana.
            reserved_excluded += 1
        else:
            pool_by_class[label_idx].append(aid)
    if reserved_excluded:
        logger.warning("%d artículos del gold reservado venían en el silver: fuera de train/val",
                       reserved_excluded)

    # --- Guardia anti-fuga: near-duplicados del test y del gold reservado fuera de train/val ---
    leaked = exclude_leaks(pool_by_class, by_id,
                           [by_id[aid] for aid in test_ids] + reserved_records)
    if leaked:
        logger.info(
            "Anti-fuga: %d near-duplicados del test o del gold reservado excluidos de train/val",
            leaked,
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
    if args.group_by_source:
        from sklearn.model_selection import StratifiedGroupKFold

        pool = [(aid, label_idx) for label_idx in sorted(pool_by_class)
                for aid in sorted(pool_by_class[label_idx])]
        # Sin `source` el artículo es su propio grupo (no arrastra a nadie).
        source_of = {aid: by_id[aid].get("source") or f"_sin_fuente_{aid}"
                     for aid, _ in pool}
        # Un medio grande que cae en val lo domina (contextoganadero llegó a
        # ser el 39 % del val y el 88 % de su doctrinarismo): los medios con
        # más del 10 % del tamaño del val van siempre a train.
        val_target = args.val_ratio * len(pool)
        size = Counter(source_of.values())
        candidates = [(aid, c) for aid, c in pool if size[source_of[aid]] <= 0.10 * val_target]
        train_ids.extend(aid for aid, _ in pool if size[source_of[aid]] > 0.10 * val_target)
        n_splits = max(2, round(len(candidates) / val_target))
        sgkf = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=args.seed)
        folds = [val_idx for _, val_idx in sgkf.split(
            candidates, [c for _, c in candidates],
            [source_of[aid] for aid, _ in candidates])]
        # Se elige el fold cuya mezcla de clases más se parece a la del pool:
        # criterio solo de datos (ningún modelo interviene). Importa para
        # doctrinarismo, que sale casi todo de medios grandes.
        pool_share = Counter(c for _, c in pool)

        def deviation(val_idx) -> float:
            share = Counter(candidates[i][1] for i in val_idx)
            return sum(abs(share[c] / len(val_idx) - n / len(pool))
                       for c, n in pool_share.items())

        val_set = set(min(folds, key=deviation).tolist())
        for i, (aid, _) in enumerate(candidates):
            (val_ids if i in val_set else train_ids).append(aid)
    else:
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
        "grouped_by": "source" if args.group_by_source else None,
        "leaked_excluded": leaked,
        "gold_reserved": len(reserved_ids),
        "reserved_excluded": reserved_excluded,
        "train": sorted(train_ids),
        "val": sorted(val_ids),
        "test": sorted(test_ids),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(splits, f, indent=2)

    # --- Split reducido para el cribado (mismo val, train estratificado) ---
    subset_ids: list[str] = []
    if args.train_subset:
        subset_path = (
            Path(args.subset_output) if args.subset_output
            else PROCESSED_DIR / "splits_cribado.json"
        )
        train_by_class: dict[int, list[str]] = defaultdict(list)
        for aid in sorted(train_ids):
            train_by_class[resolve_label_idx(by_id[aid])].append(aid)
        share = min(1.0, args.train_subset / len(train_ids))
        for label_idx in sorted(train_by_class):
            ids = train_by_class[label_idx]
            rng.shuffle(ids)
            subset_ids.extend(ids[: max(1, round(len(ids) * share))])
        with open(subset_path, "w", encoding="utf-8") as f:
            json.dump({**splits, "train": sorted(subset_ids),
                       "train_subset_of": str(output_path)}, f, indent=2)

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
    if args.group_by_source:
        medios = lambda ids: {by_id[a].get("source") for a in ids}  # noqa: E731
        print(f"  Medios: train {len(medios(train_ids))}  val {len(medios(val_ids))}"
              f"  en ambos {len(medios(train_ids) & medios(val_ids))}")
    print(f"  Gold reservado: {len(reserved_ids)}   "
          f"casi-duplicados fuera de train/val: {leaked}")
    if subset_ids:
        print(f"  Cribado: {len(subset_ids)} de train → {subset_path}")
    if invalid:
        print(f"  ⚠ {invalid} artículos con etiqueta inválida excluidos")
    print()
    print(f"  {'Clase':<18} {'train':>6} {'val':>5} {'test':>5}"
          + (f" {'cribado':>8}" if subset_ids else ""))
    train_dist = class_distribution(train_ids)
    val_dist = class_distribution(val_ids)
    test_dist = class_distribution(test_ids) if test_ids else Counter()
    subset_dist = class_distribution(subset_ids)
    for idx, cls in enumerate(IDEOLOGY_CLASSES):
        print(f"  {cls:<18} {train_dist.get(idx, 0):>6} "
              f"{val_dist.get(idx, 0):>5} {test_dist.get(idx, 0):>5}"
              + (f" {subset_dist.get(idx, 0):>8}" if subset_ids else ""))
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
