"""Calibración del ensemble contra el gold humano.

    # 1) los jueces etiquetan una muestra del gold (aquí SÍ se permite el gold:
    #    la salida va a data/silver/calibration/, nunca al silver real)
    python scripts/silver_calibrate.py run --judges gemini,claude --sample 300

    # 2) comparar contra las etiquetas humanas, con la regla que quieras
    python scripts/silver_calibrate.py report --rule majority
    python scripts/silver_calibrate.py report --rule unanimous

`report` no vuelve a llamar al LLM: recalcula el consenso sobre los veredictos
guardados, así que probar reglas es gratis.

Lo que responde: la precisión de cada juez frente al humano, el α entre
jueces, y si el acuerdo predice el acierto — que es lo que justifica (o no)
la regla de consenso antes de gastarla en 12.000 artículos.
"""

import argparse
import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import ROOT, SILVER_DIR  # noqa: E402

CALIB_DIR = SILVER_DIR / "calibration"
GOLD_LABELED = ROOT / "annotation" / "gold_set_v2_labeled.jsonl"
GOLD_ARTICLES = ROOT / "annotation" / "gold_set_v2.jsonl"


def load_gold_labels(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(
            f"✗ No existe {path}.\n  Hace falta el gold anotado: corre primero\n"
            "    python scripts/ingest_gold.py --books annotation/gold_set_v2_juan.json")
    labels = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get("label"):
                    labels[r["id"]] = r["label"]
    if not labels:
        raise SystemExit(f"✗ {path} no tiene etiquetas.")
    return labels


def cmd_run(args: argparse.Namespace) -> None:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from src.agents.silver.ensemble import label_with_ensemble
    from src.agents.silver.judges import build_judges, system_prompt_from

    gold = load_gold_labels(Path(args.gold))
    if not GOLD_ARTICLES.exists():
        raise SystemExit(f"✗ No existe {GOLD_ARTICLES}")

    # Solo artículos CON etiqueta humana: sin ella no hay contra qué medir.
    articles = [json.loads(line) for line in open(GOLD_ARTICLES, encoding="utf-8") if line.strip()]
    articles = [a for a in articles if a["id"] in gold]
    random.Random(args.seed).shuffle(articles)
    if args.sample:
        articles = articles[: args.sample]
    if not articles:
        raise SystemExit("✗ Ningún artículo del gold tiene etiqueta humana todavía.")

    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    sample_path = CALIB_DIR / "gold_sample.jsonl"
    with open(sample_path, "w", encoding="utf-8") as f:
        for a in articles:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")

    names = [n.strip() for n in args.judges.split(",") if n.strip()]
    judges = build_judges(names, system_prompt_from(args.codebook))
    print(f"Calibrando {len(judges)} jueces sobre {len(articles)} artículos del gold…")

    summary = label_with_ensemble(
        judges, input_path=sample_path, output_path=CALIB_DIR / "silver_calib.jsonl",
        rule=args.rule, exclude_ids=set(), force=True,
    )
    print(f"\n✓ Veredictos: {summary['verdicts']}")
    print(f"  {summary['labeled']} etiquetados · {summary['failed']} fallidos")
    print("\nAhora:  python scripts/silver_calibrate.py report --rule majority")


def cmd_report(args: argparse.Namespace) -> None:
    from src.agents.silver.calibration import calibrate, render_report

    verdicts_path = CALIB_DIR / "silver_calib.verdicts.jsonl"
    if not verdicts_path.exists():
        raise SystemExit(f"✗ No existe {verdicts_path}. Corre `run` primero.")
    records = [json.loads(line) for line in open(verdicts_path, encoding="utf-8") if line.strip()]
    gold = load_gold_labels(Path(args.gold))

    result = calibrate(records, gold, rule=args.rule)
    report = render_report(result)
    out = CALIB_DIR / f"report_{args.rule}.md"
    out.write_text(report, encoding="utf-8")
    (CALIB_DIR / f"report_{args.rule}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(report)
    print(f"→ {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibración del ensemble contra el gold")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Los jueces etiquetan una muestra del gold")
    p_run.add_argument("--judges", type=str, default="gemini,claude")
    p_run.add_argument("--sample", type=int, default=300,
                       help="Artículos del gold a usar (0 = todos los anotados)")
    p_run.add_argument("--seed", type=int, default=42)
    p_run.add_argument("--rule", choices=["majority", "unanimous"], default="majority")
    p_run.add_argument("--codebook", type=str, default=None)
    p_run.add_argument("--gold", type=str, default=str(GOLD_LABELED))
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report", help="Métricas contra el humano (sin LLM)")
    p_rep.add_argument("--rule", choices=["majority", "unanimous"], default="majority")
    p_rep.add_argument("--gold", type=str, default=str(GOLD_LABELED))
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for noisy in ("google_genai", "httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    args.func(args)


if __name__ == "__main__":
    main()
