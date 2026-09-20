"""El agente de Claude Code como JUEZ del silver, sin API key.

Mismo patrón que scripts/agent_filter.py, pero etiquetando las 8 clases en vez
de decidir politicidad. El agente lee lotes, escribe una clase por artículo, y
sus votos se acumulan en el mismo almacén que los de Gemini.

    next    corpus            →  lote legible para el agente
    ingest  decisiones        →  votos en el almacén de veredictos
    build   votos acumulados  →  silver set con el consenso resuelto
    status  cobertura por juez y estado del consenso

Por qué los votos se acumulan en vez de resolverse a la vez: el agente va por
lotes dentro de una sesión (con su cuota y su contexto) y Gemini recorre el
corpus de corrido. Exigir que voten simultáneamente impedía usar al agente.
Con el almacén compartido, cada uno avanza a su ritmo y `build` deriva el
consenso cuando quieras — sin gastar una llamada más.

Uso típico (el agente como uno de los jueces):

    # el agente etiqueta lo que alcance
    python scripts/silver_agent.py next --size 60
    python scripts/silver_agent.py ingest --batch 1 --decisions <archivo>

    # Gemini vota los mismos artículos, por API
    python scripts/silver_ensemble.py --judges gemini --max-articles 12000

    # y el silver sale del cruce
    python scripts/silver_agent.py build
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.silver.consensus import (  # noqa: E402
    SIN_VEREDICTO,
    mean_scores,
    resolve,
)
from src.agents.silver.judges import Verdict  # noqa: E402
from src.agents.silver.verdicts import (  # noqa: E402
    append_verdict,
    coverage,
    judged_ids,
    load_verdicts,
)
from src.core.paths import RAW_DIR, ROOT, SILVER_DIR  # noqa: E402
from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES  # noqa: E402

BATCH_DIR = SILVER_DIR / "agent_batches"
STATE_PATH = BATCH_DIR / "silver_state.json"
VERDICTS_PATH = SILVER_DIR / "verdicts.jsonl"
SILVER_PATH = SILVER_DIR / "silver_set.jsonl"
GOLD_IDS = ROOT / "annotation" / "gold_set_v2_ids.json"

JUDGE_NAME = "claude-agent"
JUDGE_FAMILY = "claude"

# Cuánto texto ve el agente. La clase dominante se decide por el encuadre, que
# el codebook sitúa en el titular y el primer tercio; mandar el artículo
# completo multiplicaría el coste en contexto sin mejorar la decisión.
HEAD_CHARS = 2200

# Presupuesto por tanda, en tokens de TEXTO entregado. No es el contexto
# entero: el agente gasta además instrucciones y sus propias respuestas.
DEFAULT_BUDGET_TOKENS = 120_000

DOUBT_TOKEN = "dud"
ALIASES = {
    "pop": "populismo", "inst": "institucionalismo", "pers": "personalismo",
    "doc": "doctrinarismo", "sob": "soberanismo", "glob": "globalismo",
    "cons": "conservadurismo", "prog": "progresismo",
}


# --------------------------------------------------------------- estado --

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_state(input_path: Path) -> dict:
    """Estado de la travesía. Si cambia el corpus de entrada, se reinicia.

    El cursor es un número de LÍNEA: apuntar a otro archivo lo vuelve
    insignificante y arrastrarlo saltaría artículos en silencio.
    """
    default = {"input": str(input_path), "cursor": 0, "batch_seq": 1,
               "session_tokens": 0, "budget_tokens": DEFAULT_BUDGET_TOKENS,
               "pending_batch": None, "updated_at": None}
    if not STATE_PATH.exists():
        return default
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    return default if state.get("input") != str(input_path) else {**default, **state}


def write_state(state: dict) -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def load_corpus(path: Path) -> list[dict]:
    """Carga el JSONL anotando el nº de línea de cada artículo en `_line`."""
    articles = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                continue
            article["_line"] = lineno
            articles.append(article)
    return articles


def load_gold_ids() -> set[str]:
    if not GOLD_IDS.exists():
        return set()
    data = json.loads(GOLD_IDS.read_text(encoding="utf-8"))
    return set(data if isinstance(data, list) else data.get("ids", []))


# ---------------------------------------------------------------- lotes --

def write_batch(sample: list[dict], batch_num: int, input_path: Path) -> tuple[Path, int]:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = BATCH_DIR / f"lote_{batch_num:03d}.txt"
    manifest_path = BATCH_DIR / f"lote_{batch_num:03d}.manifest.json"

    lines, manifest = [], []
    for n, article in enumerate(sample, start=1):
        title = (article.get("title") or "(sin título)").strip()
        body = " ".join((article.get("text") or "").split())[:HEAD_CHARS]
        # Sin la fuente: el codebook exige juzgar por el texto, y saber de
        # qué medio viene sesga el encuadre que uno cree ver.
        lines += [f"[{n}]", title, body, ""]
        manifest.append({"n": n, "id": article.get("id"), "line": article.get("_line")})

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"batch": batch_num, "input": str(input_path), "items": manifest},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    return txt_path, sum(len(line) for line in lines) // 4


def parse_decisions(text: str) -> tuple[dict[int, dict], list[str]]:
    """Parsea «n clase [confianza]». Devuelve (decisiones, errores).

    Recoge los errores en vez de reventar en la primera línea mala: un typo en
    el artículo 50 no debe tirar los 49 anteriores.
    """
    decisiones: dict[int, dict] = {}
    errores: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            errores.append(f"línea {lineno}: faltan campos → {raw.strip()!r}")
            continue
        token = parts[0].strip("[]().")
        if not token.isdigit():
            errores.append(f"línea {lineno}: '{parts[0]}' no es un número")
            continue
        n = int(token)
        if n in decisiones:
            errores.append(f"línea {lineno}: el artículo {n} ya tenía decisión")
            continue

        crudo = parts[1].lower()
        if crudo in (DOUBT_TOKEN, "duda", "?"):
            clase = None          # abstención explícita: se registra sin voto
        else:
            clase = ALIASES.get(crudo, crudo)
            if clase not in CLASS_TO_IDX:
                errores.append(f"línea {lineno}: clase desconocida '{parts[1]}'")
                continue

        confianza = 0.8
        for extra in parts[2:]:
            try:
                confianza = max(0.0, min(1.0, float(extra)))
            except ValueError:
                errores.append(f"línea {lineno}: '{extra}' no es una confianza")
        decisiones[n] = {"clase": clase, "confianza": confianza}
    return decisiones, errores


# ------------------------------------------------------------- comandos --

def cmd_next(args: argparse.Namespace) -> None:
    input_path = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    if not input_path.exists():
        raise SystemExit(f"✗ No existe {input_path}")

    state = read_state(input_path)
    if args.reset_session:
        state["session_tokens"] = 0
    if args.budget is not None:
        state["budget_tokens"] = args.budget

    if state.get("pending_batch") and not args.force:
        raise SystemExit(
            f"✗ El lote {state['pending_batch']} sigue sin ingerir.\n"
            f"  Termínalo:  python scripts/silver_agent.py ingest "
            f"--batch {state['pending_batch']} --decisions <archivo>\n"
            "  O usa --force para rehacerlo.")

    articles = load_corpus(input_path)
    total = len(articles)
    # El gold es el conjunto de PRUEBA: nunca recibe etiqueta silver.
    excluidos = load_gold_ids()
    ya_votados = judged_ids(VERDICTS_PATH, judge=JUDGE_NAME)

    pendientes = [a for a in articles
                  if a["_line"] >= state["cursor"]
                  and a.get("id") not in excluidos
                  and a.get("id") not in ya_votados]
    if not pendientes:
        write_state({**state, "pending_batch": None})
        print(f"✓ El agente ya votó todo lo elegible de {total:,} artículos.")
        print("  Siguiente:  python scripts/silver_agent.py build")
        return

    if args.max_articles:
        restante = args.max_articles - len(ya_votados)
        if restante <= 0:
            print(f"✓ Alcanzado el tope de {args.max_articles:,} artículos "
                  f"({len(ya_votados):,} votados).")
            return
        pendientes = pendientes[:restante]

    batch = pendientes[:args.size]
    estimado = sum(min(len(a.get("text") or ""), HEAD_CHARS)
                   + len(a.get("title") or "") for a in batch) // 4

    # El corte se decide ANTES de entregar: entregar y avisar después ya
    # habría gastado el contexto que el presupuesto protege.
    gastado = state["session_tokens"]
    if gastado > 0 and gastado + estimado > state["budget_tokens"]:
        write_state(state)
        print("⏹  PRESUPUESTO DE LA TANDA AGOTADO — para aquí.")
        print(f"   Entregados: {gastado:,} de {state['budget_tokens']:,} tokens")
        print(f"   Votados por el agente: {len(ya_votados):,}  ·  "
              f"pendientes: {len(pendientes):,}")
        print("\n   Retomar:  python scripts/silver_agent.py next --reset-session")
        return

    batch_num = state["batch_seq"]
    txt_path, tokens = write_batch(batch, batch_num, input_path)
    state.update({"batch_seq": batch_num + 1,
                  "session_tokens": gastado + tokens,
                  "pending_batch": batch_num})
    write_state(state)

    print(f"LOTE {batch_num}: {len(batch)} artículos → {txt_path}")
    print(f"  votados por el agente  {len(ya_votados):,}"
          + (f" de {args.max_articles:,}" if args.max_articles else ""))
    print(f"  tanda                  {state['session_tokens']:,}/"
          f"{state['budget_tokens']:,} tokens")
    if state["budget_tokens"] - state["session_tokens"] < tokens:
        print("  ⚠ último lote de la tanda: al ingerirlo, para y reporta")
    print(f"  ingerir   python scripts/silver_agent.py ingest --batch {batch_num} "
          "--decisions <archivo>")


def cmd_ingest(args: argparse.Namespace) -> None:
    manifest_path = BATCH_DIR / f"lote_{args.batch:03d}.manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"✗ No existe {manifest_path}. ¿Sacaste el lote?")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_n = {item["n"]: item for item in manifest["items"]}

    decisiones, errores = parse_decisions(
        Path(args.decisions).read_text(encoding="utf-8"))
    if errores:
        print(f"⚠ {len(errores)} líneas ilegibles (se omiten):")
        for e in errores[:10]:
            print(f"    {e}")
        print()

    desconocidas = sorted(set(decisiones) - set(by_n))
    if desconocidas:
        print(f"⚠ {len(desconocidas)} decisiones no son de este lote: {desconocidas[:8]}")
        for n in desconocidas:
            decisiones.pop(n)

    faltan = sorted(set(by_n) - set(decisiones))
    if faltan and not args.partial:
        raise SystemExit(
            f"✗ Faltan {len(faltan)} de {len(by_n)} decisiones (p. ej. {faltan[:8]}).\n"
            "  Complétalas, o usa --partial para ingerir solo las presentes.")

    conteo: Counter = Counter()
    for n in sorted(decisiones):
        item, d = by_n[n], decisiones[n]
        clase = d["clase"]
        # Una abstención se registra como voto inválido: deja rastro de que el
        # agente LO VIO y no supo decidir, que es distinto de no haberlo visto.
        verdict = Verdict(
            judge=JUDGE_NAME, model=args.model, family=JUDGE_FAMILY,
            dominant=clase, ok=clase is not None,
            error=None if clase else "duda del anotador",
            scores={c: (d["confianza"] if c == clase else
                        round((1 - d["confianza"]) / 7, 4)) for c in IDEOLOGY_CLASSES}
            if clase else {},
        )
        append_verdict(VERDICTS_PATH, item["id"], verdict)
        conteo[clase or DOUBT_TOKEN] += 1

    # El cursor solo avanza al ingerir: si la sesión se corta a mitad de lote,
    # esos artículos vuelven a salir en vez de perderse.
    input_path = Path(manifest["input"])
    state = read_state(input_path)
    if state.get("pending_batch") == args.batch:
        lineas = [i["line"] for i in manifest["items"] if i.get("line") is not None]
        if lineas:
            state["cursor"] = max(state["cursor"], max(lineas) + 1)
        state["pending_batch"] = None
        write_state(state)

    if not args.keep_batch:
        for p in (BATCH_DIR / f"lote_{args.batch:03d}.txt", manifest_path,
                  Path(args.decisions)):
            p.unlink(missing_ok=True)

    print(f"✓ {sum(conteo.values()):,} votos → {VERDICTS_PATH}  (juez={JUDGE_NAME})")
    for clase, n in conteo.most_common():
        print(f"    {clase:20} {n:,}")
    print(f"  cursor → línea {state['cursor']:,}")
    print(f"\n  Cobertura por juez: {coverage(VERDICTS_PATH)}")


def cmd_build(args: argparse.Namespace) -> None:
    """Deriva el silver del cruce de todos los votos acumulados."""
    input_path = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    output_path = Path(args.output) if args.output else SILVER_PATH
    votos = load_verdicts(VERDICTS_PATH)
    if not votos:
        raise SystemExit(f"✗ No hay veredictos en {VERDICTS_PATH}.")

    excluidos = load_gold_ids()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: si esto se corta, el silver bueno sigue intacto.
    tmp = output_path.with_suffix(output_path.suffix + ".tmp")

    estados: Counter = Counter()
    escritos = aceptados = 0
    with open(input_path, encoding="utf-8") as fin, open(tmp, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            aid = raw.get("id")
            if not aid or aid in excluidos or aid not in votos:
                continue

            c = resolve(votos[aid], args.rule)
            estados[c.status] += 1
            if c.status == SIN_VEREDICTO or c.label is None:
                continue
            if args.only_accepted and not c.accepted:
                continue

            fout.write(json.dumps({
                "id": aid, "text": raw["text"], "title": raw.get("title", ""),
                "source": raw.get("source", ""), "category": raw.get("category", ""),
                "url": raw.get("url", ""), "date": raw.get("date"),
                "label": c.label, "label_idx": CLASS_TO_IDX[c.label],
                "label_source": "silver-ensemble",
                "judge_models": [v.model for v in votos[aid] if v.ok],
                "consensus": c.to_dict(),
                **mean_scores(votos[aid]),
            }, ensure_ascii=False) + "\n")
            escritos += 1
            aceptados += int(c.accepted)
    tmp.replace(output_path)

    print(f"✓ {escritos:,} artículos → {output_path}")
    print(f"  aceptados por la regla '{args.rule}': {aceptados:,}"
          f"  ·  con etiqueta pero no aceptados: {escritos - aceptados:,}")
    for estado, n in estados.most_common():
        print(f"    {estado:16} {n:,}")
    print(f"\n  Cobertura por juez: {coverage(VERDICTS_PATH)}")
    if escritos and aceptados / escritos < 0.5:
        print("\n  ⚠ Menos de la mitad supera la regla. Antes de filtrar por")
        print("    `accepted`, mira si el acuerdo predice el acierto:")
        print("      python scripts/silver_calibrate.py report --rule majority")


def cmd_status(args: argparse.Namespace) -> None:
    input_path = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    state = read_state(input_path)
    votos = load_verdicts(VERDICTS_PATH)
    excluidos = load_gold_ids()
    total = sum(1 for line in open(input_path, encoding="utf-8") if line.strip())
    elegibles = total - len(excluidos)

    print("=" * 62)
    print("  SILVER — ESTADO")
    print("=" * 62)
    print(f"  corpus            {total:,}  ·  elegibles {elegibles:,} "
          f"(gold excluido: {len(excluidos):,})")
    print(f"  con algún voto    {len(votos):,}")
    print("\n  Cobertura por juez:")
    for juez, n in sorted(coverage(VERDICTS_PATH).items(), key=lambda kv: -kv[1]):
        print(f"    {juez:20} {n:,}")
    if not votos:
        print("    (ninguno todavía)")

    estados = Counter(resolve(v, args.rule).status for v in votos.values())
    if estados:
        print(f"\n  Consenso con la regla '{args.rule}':")
        for estado, n in estados.most_common():
            print(f"    {estado:16} {n:,}")

    print(f"\n  Agente: cursor línea {state['cursor']:,} · próximo lote "
          f"{state['batch_seq']}")
    if state.get("pending_batch"):
        print(f"    ⚠ lote {state['pending_batch']} entregado y SIN ingerir")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="El agente de Claude Code como juez del silver")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_next = sub.add_parser("next", help="Siguiente lote para el agente")
    p_next.add_argument("--size", type=int, default=60)
    p_next.add_argument("--input", type=str, default=None)
    p_next.add_argument("--max-articles", type=int, default=None,
                        help="Tope de artículos que votará el agente en total")
    p_next.add_argument("--budget", type=int, default=None,
                        help=f"Tokens de texto por tanda (default {DEFAULT_BUDGET_TOKENS:,})")
    p_next.add_argument("--reset-session", action="store_true",
                        help="Empieza una tanda nueva (ponlo al abrir sesión)")
    p_next.add_argument("--force", action="store_true")
    p_next.set_defaults(func=cmd_next)

    p_ing = sub.add_parser("ingest", help="Volcar las decisiones al almacén")
    p_ing.add_argument("--batch", type=int, required=True)
    p_ing.add_argument("--decisions", type=str, required=True)
    p_ing.add_argument("--model", type=str, default="claude-code-agent")
    p_ing.add_argument("--partial", action="store_true")
    p_ing.add_argument("--keep-batch", action="store_true")
    p_ing.set_defaults(func=cmd_ingest)

    p_build = sub.add_parser("build", help="Derivar el silver de los votos")
    p_build.add_argument("--rule", choices=["majority", "unanimous"], default="majority")
    p_build.add_argument("--input", type=str, default=None)
    p_build.add_argument("--output", type=str, default=None)
    p_build.add_argument("--only-accepted", action="store_true",
                         help="Escribir SOLO lo que supera la regla. Ojo: descartar "
                              "el desacuerdo deja el silver más fácil que el gold")
    p_build.set_defaults(func=cmd_build)

    p_st = sub.add_parser("status", help="Cobertura y consenso")
    p_st.add_argument("--rule", choices=["majority", "unanimous"], default="majority")
    p_st.add_argument("--input", type=str, default=None)
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
