"""Silver set por ensemble de jueces: varios LLM por artículo + consenso.

    python scripts/silver_ensemble.py --judges gemini,claude --max-articles 12000
    python scripts/silver_ensemble.py --judges gemini,claude --codebook docs/codebook_juan.md
    python scripts/silver_ensemble.py --judges gemini --rule unanimous --max-articles 300

El gold (annotation/gold_set_v2_ids.json) queda fuera por defecto: es el
conjunto de prueba. Reanudable: relanzar el mismo comando continúa.

Antes de los 12.000, corre la calibración sobre el gold ya anotado
(scripts/silver_calibrate.py) y fija la regla con datos, no a ojo.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import RAW_DIR, ROOT, SILVER_DIR  # noqa: E402

logger = logging.getLogger("silver_ensemble")


def load_gold_ids(path: Path | None) -> set[str]:
    path = path or ROOT / "annotation" / "gold_set_v2_ids.json"
    if not path.exists():
        logger.warning("No encontré %s: NINGÚN artículo quedará fuera del silver. "
                       "Si ya hay gold muestreado, esto contamina el test.", path)
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data if isinstance(data, list) else data.get("ids", []))


def main() -> None:
    parser = argparse.ArgumentParser(description="Silver por ensemble de jueces LLM")
    parser.add_argument("--judges", type=str, default="gemini,claude",
                        help="Jueces separados por coma (ver JUDGE_REGISTRY). "
                             "Mezcla familias: el acuerdo entre clones no es evidencia")
    parser.add_argument("--rule", choices=["majority", "unanimous"], default="majority")
    parser.add_argument("--codebook", type=str, default=None,
                        help="Archivo con el codebook a usar como prompt (p. ej. el "
                             "del anotador). Sin él, el del proyecto")
    parser.add_argument("--max-articles", type=int, default=None)
    parser.add_argument("--input", type=str, default=None)
    parser.add_argument("--output", type=str, default=None,
                        help="default: data/silver/silver_set.jsonl")
    parser.add_argument("--gold-ids", type=str, default=None)
    parser.add_argument("--allow-gold-in-silver", action="store_true",
                        help="Etiquetar también el gold. Contamina el test; solo pruebas")
    parser.add_argument("--force", action="store_true", help="Rehacer desde cero")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("google_genai", "httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from src.agents.silver.ensemble import label_with_ensemble
    from src.agents.silver.judges import build_judges, families, system_prompt_from

    names = [n.strip() for n in args.judges.split(",") if n.strip()]
    prompt = system_prompt_from(args.codebook)
    judges = build_judges(names, prompt)

    exclude = set() if args.allow_gold_in_silver else load_gold_ids(
        Path(args.gold_ids) if args.gold_ids else None)

    input_path = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    output_path = Path(args.output) if args.output else SILVER_DIR / "silver_set.jsonl"

    print("=" * 66)
    print("  SILVER POR ENSEMBLE")
    print(f"  Jueces:     {', '.join(f'{j.name} ({j.model})' for j in judges)}")
    print(f"  Familias:   {', '.join(sorted(families(judges)))}"
          + ("   ⚠ una sola: acuerdo ≠ evidencia" if len(families(judges)) == 1 else ""))
    print(f"  Regla:      {args.rule}")
    print(f"  Codebook:   {args.codebook or 'el del proyecto'}")
    print(f"  Gold fuera: {len(exclude):,} artículos" if exclude else "  Gold fuera: NINGUNO ⚠")
    print(f"  Entrada:    {input_path.name}")
    print(f"  Salida:     {output_path}")
    print("=" * 66)

    summary = label_with_ensemble(
        judges, input_path=input_path, output_path=output_path, rule=args.rule,
        exclude_ids=exclude, max_articles=args.max_articles, force=args.force,
    )

    print()
    print("=" * 66)
    print(f"  Etiquetados: {summary['labeled']:,}   aceptados por la regla: {summary['accepted']:,}")
    print(f"  Excluidos (gold): {summary['excluded']:,}   fallidos: {summary['failed']:,}")
    for status, n in sorted(summary["status"].items(), key=lambda kv: -kv[1]):
        print(f"    {status:16} {n:,}")
    if summary["retired_judges"]:
        print(f"  ⚠ Jueces retirados por cuota: {', '.join(summary['retired_judges'])}")
    print(f"  Cursor: {summary['cursor']:,} / {summary['total']:,}")
    print(f"  Veredictos: {summary.get('verdicts')}")
    print("=" * 66)


if __name__ == "__main__":
    main()
