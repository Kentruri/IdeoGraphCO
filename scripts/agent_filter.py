"""Filtrado hecho por el AGENTE de Claude Code, sin API ni créditos.

Claude Code no puede llamarse a sí mismo por API: el agente lee archivos y
escribe archivos. Este script es el puente en esas dos direcciones.

    export   corpus  →  lote legible que el agente clasifica en la sesión
    ingest   decisiones del agente  →  logs/filter_decisions.jsonl
    compare  concordancia entre dos motores sobre los artículos que ambos vieron

**Para qué sirve realmente.** Leer los 50.351 artículos en la sesión cuesta
~15,9 millones de tokens solo de texto: no es viable clasificarlos todos así.
Lo que sí rinde es usar al agente como MAESTRO de unos cientos de casos:

  1. `export` una muestra estratificada por fuente
  2. el agente la clasifica (decisiones en un .txt)
  3. `ingest` las vuelca al log de decisiones
  4. `scripts/train_prefilter.py` aprende de ellas y resuelve gratis, en
     local, la mayor parte del corpus
  5. `scripts/filter_corpus.py --prefilter` deja al LLM solo la zona gris

Es el mismo patrón teacher→student que ya documenta `src/scraper/prefilter.py`,
con el agente como maestro en vez de Gemini.

`compare` cubre el otro uso: medir cuánto coinciden dos motores sobre los
mismos artículos (Krippendorff α). Si el corpus se filtra a medias entre
Gemini y el agente, esa cifra es lo que justifica tratar ambas mitades como
comparables — y es material citable en el informe.

Uso:
    python scripts/agent_filter.py export --limit 400
    #  → data/agent_batches/lote_001.txt  (el agente lo lee y decide)
    python scripts/agent_filter.py ingest --batch 1 --decisions decisiones.txt
    python scripts/agent_filter.py compare --a claude-agent --b llm
"""

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.gold.agreement import (  # noqa: E402
    krippendorff_alpha,
    percent_agreement,
)
from src.core.paths import DATA_DIR, LOGS_DIR, RAW_DIR  # noqa: E402
from src.scraper.article_filter import (  # noqa: E402
    BLOCKING_TEXT_ISSUES,
    FILTER_CATEGORIES,
    TEXT_ISSUES,
)

BATCH_DIR = DATA_DIR / "agent_batches"
STATE_PATH = BATCH_DIR / "filter_state.json"

# Presupuesto por defecto, en tokens de TEXTO DE ARTÍCULO entregados al
# agente en una tanda. No es el contexto entero: el agente gasta además
# instrucciones, razonamiento y sus propias respuestas. 120k de texto deja
# margen cómodo en una ventana de 200k, que es el caso peor.
DEFAULT_BUDGET_TOKENS = 120_000


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_state(input_path: Path) -> dict:
    """Estado de la travesía. Si cambia el corpus de entrada, se reinicia.

    El cursor es un número de LÍNEA del JSONL de entrada: si alguien apunta a
    otro archivo, ese número deja de significar nada y arrastrarlo saltaría
    artículos en silencio.
    """
    default = {
        "input": str(input_path),
        "cursor": 0,
        "batch_seq": next_batch_number(),
        "session_tokens": 0,
        "budget_tokens": DEFAULT_BUDGET_TOKENS,
        "pending_batch": None,
        "updated_at": None,
    }
    if not STATE_PATH.exists():
        return default
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if state.get("input") != str(input_path):
        return default
    return {**default, **state}


def write_state(state: dict) -> None:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now()
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# Abreviaturas: el agente escribe una línea por artículo y su salida también
# consume tokens. `pol` en vez de `political_article` recorta ~4 tokens por
# línea, que sobre miles de artículos es una diferencia real.
DOUBT_TOKEN = "dud"

CATEGORY_ALIASES = {
    "pol": "political_article",
    "for": "political_foreign",
    "non": "nonpolitical_article",
    "bio": "biography_static",
    "gar": "garbage",
}
ISSUE_ALIASES = {
    "br": "boilerplate_residual",
    "dg": "digest_multinoticia",
    "tr": "truncado",
    "pw": "preview_paywall",
}

# Cuánto texto ve el agente. El filtro decide politicidad y colombianidad, y
# ambas se resuelven casi siempre en el titular y la entradilla; mandar el
# artículo completo multiplicaría el costo sin mejorar la decisión.
_HEAD_CHARS = 1200
# El mismo recorte que usa el filtro LLM, para que el text_head guardado
# entrene al prefilter con la entrada que este verá en producción.
_LOG_HEAD_CHARS = 3000


def load_corpus(path: Path) -> list[dict]:
    """Carga el JSONL anotando el nº de línea de cada artículo en `_line`.

    El cursor de la travesía es un número de línea, así que cada artículo
    tiene que saber de dónde salió para poder avanzarlo al ingerir el lote.
    """
    articles = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f):
            line = line.strip()
            if line:
                try:
                    article = json.loads(line)
                except json.JSONDecodeError:
                    continue
                article["_line"] = lineno
                articles.append(article)
    return articles


def decided_ids(log_path: Path, engine: str | None = None) -> set[str]:
    """Ids ya decididos en el log (opcionalmente por un motor concreto)."""
    seen: set[str] = set()
    if not log_path.exists():
        return seen
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if engine and entry.get("engine") != engine:
                continue
            if entry.get("id"):
                seen.add(entry["id"])
    return seen


def stratified_sample(articles: list[dict], limit: int, seed: int) -> list[dict]:
    """Reparte el cupo entre fuentes en vez de tomar las primeras N líneas.

    El JSONL sale ordenado por rondas de recolección, así que un corte por
    cabecera sobre-representa a las fuentes rápidas. El prefilter aprendido
    de esa muestra heredaría el sesgo y trataría "fuente" como si fuera
    "politicidad".
    """
    by_source: dict[str, list[dict]] = defaultdict(list)
    for article in articles:
        by_source[article.get("source", "?")].append(article)

    rng = random.Random(seed)
    for bucket in by_source.values():
        rng.shuffle(bucket)

    chosen: list[dict] = []
    sources = sorted(by_source)
    # Ronda a ronda, un artículo por fuente: con cupos pequeños garantiza
    # cobertura amplia antes de profundizar en ninguna fuente.
    depth = 0
    while len(chosen) < limit:
        added = False
        for name in sources:
            if depth < len(by_source[name]):
                chosen.append(by_source[name][depth])
                added = True
                if len(chosen) >= limit:
                    break
        if not added:
            break
        depth += 1
    rng.shuffle(chosen)
    return chosen


def write_batch(sample: list[dict], batch_num: int, input_path: Path) -> tuple[Path, int]:
    """Escribe lote_NNN.txt + su manifiesto. Devuelve (ruta, tokens estimados)."""
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = BATCH_DIR / f"lote_{batch_num:03d}.txt"
    manifest_path = BATCH_DIR / f"lote_{batch_num:03d}.manifest.json"

    lines, manifest = [], []
    for n, article in enumerate(sample, start=1):
        title = (article.get("title") or "(sin título)").strip()
        body = " ".join((article.get("text") or "").split())[:_HEAD_CHARS]
        lines.append(f"[{n}] {article.get('source', '?')}")
        lines.append(title)
        lines.append(body)
        lines.append("")
        manifest.append({"n": n, "id": article.get("id"),
                         "url": article.get("url"),
                         "source": article.get("source"),
                         "line": article.get("_line")})

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"batch": batch_num, "input": str(input_path),
                    "items": manifest}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return txt_path, sum(len(line) for line in lines) // 4


def next_batch_number() -> int:
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    existing = [int(p.stem.split("_")[-1]) for p in BATCH_DIR.glob("lote_*.txt")
                if p.stem.split("_")[-1].isdigit()]
    return max(existing, default=0) + 1


def cmd_export(args: argparse.Namespace) -> None:
    input_path = Path(args.input) if args.input else RAW_DIR / "articles_unfiltered.jsonl"
    if not input_path.exists():
        raise SystemExit(f"✗ No existe {input_path}")

    articles = load_corpus(input_path)
    log_path = LOGS_DIR / "filter_decisions.jsonl"

    if args.overlap_with:
        # Modo auditoría: se muestrea SOLO entre lo que el otro motor ya
        # decidió, porque sin solape no hay concordancia que medir.
        pool_ids = decided_ids(log_path, engine=args.overlap_with)
        articles = [a for a in articles if a.get("id") in pool_ids]
        if not articles:
            raise SystemExit(
                f"✗ El motor '{args.overlap_with}' no tiene decisiones en "
                f"{log_path}. Filtra primero con él."
            )
    elif not args.allow_redo:
        already = decided_ids(log_path)
        articles = [a for a in articles if a.get("id") not in already]
        if not articles:
            raise SystemExit("✓ Todos los artículos ya tienen decisión.")

    sample = stratified_sample(articles, args.limit, args.seed)

    batch_num = args.batch or next_batch_number()
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = BATCH_DIR / f"lote_{batch_num:03d}.txt"
    manifest_path = BATCH_DIR / f"lote_{batch_num:03d}.manifest.json"

    lines = []
    manifest = []
    for n, article in enumerate(sample, start=1):
        title = (article.get("title") or "(sin título)").strip()
        body = " ".join((article.get("text") or "").split())[:_HEAD_CHARS]
        lines.append(f"[{n}] {article.get('source', '?')}")
        lines.append(title)
        lines.append(body)
        lines.append("")
        manifest.append({"n": n, "id": article.get("id"),
                         "url": article.get("url"),
                         "source": article.get("source"),
                         "line": article.get("_line")})

    txt_path.write_text("\n".join(lines), encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"batch": batch_num, "input": str(input_path),
                    "items": manifest}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    approx_tokens = sum(len(line) for line in lines) // 4
    print(f"✓ Lote {batch_num}: {len(sample):,} artículos → {txt_path}")
    print(f"  manifiesto: {manifest_path.name}")
    print(f"  ~{approx_tokens:,} tokens de lectura para el agente")
    print(f"  fuentes distintas: {len({a.get('source') for a in sample})}")
    print()
    print("  Siguiente: pide al agente que lea el lote y escriba las")
    print("  decisiones (una línea por artículo: «n categoría [conf] [issues]»),")
    print(f"  y luego:  python scripts/agent_filter.py ingest --batch {batch_num} \\")
    print("              --decisions <archivo>")


def parse_decisions(text: str) -> tuple[dict[int, dict], list[str]]:
    """Parsea «n categoría [confianza] [issues]», una línea por artículo.

    Tolera la forma abreviada y la completa, comentarios con `#` y líneas en
    blanco. Devuelve (decisiones, errores) en vez de reventar en la primera
    línea mala: un typo en el artículo 300 no debe tirar las 299 anteriores.
    """
    decisions: dict[int, dict] = {}
    errors: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.replace(",", " ").split()
        if len(parts) < 2:
            errors.append(f"línea {lineno}: faltan campos → {raw.strip()!r}")
            continue
        token = parts[0].strip("[]().")
        if not token.isdigit():
            errors.append(f"línea {lineno}: '{parts[0]}' no es un número")
            continue
        n = int(token)

        raw_category = parts[1].lower()
        if raw_category in (DOUBT_TOKEN, "duda", "?"):
            # No es una categoría: es una abstención explícita. Se resuelve
            # con Gemini en `ingest`, no aquí.
            category = DOUBT_TOKEN
        else:
            category = CATEGORY_ALIASES.get(raw_category, raw_category)
        if category != DOUBT_TOKEN and category not in FILTER_CATEGORIES:
            errors.append(f"línea {lineno}: categoría desconocida '{parts[1]}'")
            continue

        confidence = 0.9
        issues: list[str] = []
        for extra in parts[2:]:
            try:
                confidence = float(extra)
                continue
            except ValueError:
                pass
            issue = ISSUE_ALIASES.get(extra.lower(), extra.lower())
            if issue in TEXT_ISSUES:
                issues.append(issue)
            else:
                errors.append(f"línea {lineno}: marca desconocida '{extra}'")
        if n in decisions:
            errors.append(f"línea {lineno}: el artículo {n} ya tenía decisión")
            continue
        decisions[n] = {
            "category": category,
            "confidence": max(0.0, min(1.0, confidence)),
            "text_issues": issues,
        }
    return decisions, errors


def cmd_next(args: argparse.Namespace) -> None:
    """Entrega el siguiente lote de la travesía completa del corpus.

    A diferencia de `export` (muestra estratificada, para calibrar), esto
    recorre el corpus EN ORDEN desde el cursor: el objetivo es no dejar
    ningún artículo sin decidir.
    """
    input_path = Path(args.input) if args.input else RAW_DIR / "articles_unfiltered.jsonl"
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
            f"  Termínalo:  python scripts/agent_filter.py ingest "
            f"--batch {state['pending_batch']} --decisions <archivo>\n"
            "  O usa --force para descartarlo y rehacerlo."
        )

    articles = load_corpus(input_path)
    total = len(articles)
    already = decided_ids(LOGS_DIR / "filter_decisions.jsonl")

    pending = [a for a in articles
               if a["_line"] >= state["cursor"] and a.get("id") not in already]
    if not pending:
        write_state({**state, "pending_batch": None})
        print(f"✓ Travesía completa: los {total:,} artículos tienen decisión.")
        print("  Siguiente: python scripts/filter_corpus.py --prefer-engine claude-agent")
        return

    batch = pending[:args.size]
    estimated = sum(min(len(a.get("text") or ""), _HEAD_CHARS)
                    + len(a.get("title") or "") for a in batch) // 4

    # El corte se decide ANTES de entregar el lote: entregarlo y luego avisar
    # de que no hay presupuesto ya habría gastado el contexto que se quería
    # proteger.
    spent = state["session_tokens"]
    if spent > 0 and spent + estimated > state["budget_tokens"]:
        write_state(state)
        print("⏹  PRESUPUESTO DE LA TANDA AGOTADO — para aquí.")
        print(f"   Entregados en esta tanda: {spent:,} de "
              f"{state['budget_tokens']:,} tokens")
        print(f"   Cursor: línea {state['cursor']:,} de {total:,}")
        print(f"   Decididos: {len(already):,}  ·  faltan {len(pending):,}")
        print()
        print("   Para retomar en una sesión nueva:")
        print("     python scripts/agent_filter.py next --reset-session")
        return

    batch_num = state["batch_seq"]
    txt_path, tokens = write_batch(batch, batch_num, input_path)
    state["batch_seq"] = batch_num + 1
    state["session_tokens"] = spent + tokens
    state["pending_batch"] = batch_num
    write_state(state)

    done = total - len(pending)
    pct = 100 * done / total if total else 0
    print(f"LOTE {batch_num}: {len(batch)} artículos → {txt_path}")
    print(f"  progreso   {done:,}/{total:,} ({pct:.1f}%)  ·  faltan {len(pending):,}")
    print(f"  tanda      {state['session_tokens']:,}/{state['budget_tokens']:,} tokens")
    restante = state["budget_tokens"] - state["session_tokens"]
    if restante < tokens:
        print("  ⚠ este es el ÚLTIMO lote de la tanda: al ingerirlo, para y "
              "reporta el cursor")
    print(f"  ingerir    python scripts/agent_filter.py ingest --batch {batch_num} "
          "--decisions <archivo>")


def cmd_status(args: argparse.Namespace) -> None:
    input_path = Path(args.input) if args.input else RAW_DIR / "articles_unfiltered.jsonl"
    if not input_path.exists():
        raise SystemExit(f"✗ No existe {input_path}")
    state = read_state(input_path)
    log_path = LOGS_DIR / "filter_decisions.jsonl"

    total = sum(1 for line in open(input_path, encoding="utf-8") if line.strip())
    by_engine: Counter = Counter()
    kept = 0
    seen: set[str] = set()
    if log_path.exists():
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not entry.get("id") or entry["id"] in seen:
                    continue
                seen.add(entry["id"])
                by_engine[entry.get("engine", "?")] += 1
                kept += bool(entry.get("kept"))

    done = len(seen)
    pct = 100 * done / total if total else 0

    if args.json:
        # El servicio desatendido decide si hubo avance comparando `decided`
        # entre corridas: parsear la salida bonita sería frágil.
        print(json.dumps({
            "total": total, "decided": done, "remaining": total - done,
            "kept": kept, "pct": round(pct, 3),
            "cursor": state["cursor"], "batch_seq": state["batch_seq"],
            "pending_batch": state.get("pending_batch"),
            "by_engine": dict(by_engine),
        }, ensure_ascii=False))
        return

    bar = "█" * int(pct / 2.5) + "·" * (40 - int(pct / 2.5))
    print("=" * 66)
    print("  TRAVESÍA DEL CORPUS")
    print("=" * 66)
    print(f"  {bar}  {pct:5.1f}%")
    print(f"  decididos   {done:,} de {total:,}   ·   faltan {total - done:,}")
    print(f"  conservados {kept:,} ({100 * kept / done:.1f}% de lo decidido)"
          if done else "  conservados 0")
    print(f"  cursor      línea {state['cursor']:,}")
    print(f"  próximo     lote {state['batch_seq']}")
    if state.get("pending_batch"):
        print(f"  ⚠ lote {state['pending_batch']} entregado y SIN ingerir")
    print(f"  tanda       {state['session_tokens']:,}/"
          f"{state['budget_tokens']:,} tokens")
    print("\n  Por motor:")
    for engine, n in by_engine.most_common():
        print(f"    {engine:24} {n:,}")
    if done < total:
        remaining_batches = -(-(total - done) // 60)
        print(f"\n  A 60 por lote faltan ~{remaining_batches:,} lotes.")


def resolve_doubts(doubtful: list[tuple[int, dict]], corpus: dict,
                   by_n: dict, model: str, rate_limit: float) -> dict[int, dict]:
    """Desempata con Gemini SOLO los artículos que el agente marcó `dud`.

    El agente decide el corpus entero; Gemini interviene únicamente donde la
    duda es genuina. Así el criterio dominante es uno solo (el del codebook
    aplicado por el agente) y el segundo motor no reabre casos ya resueltos:
    entra donde no había decisión que contradecir.
    """
    if not doubtful:
        return {}

    import time

    from dotenv import load_dotenv

    from src.scraper.article_filter import is_real_article
    from src.scraper.llm_providers import build_provider_chain

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    try:
        chain = build_provider_chain(["gemini"])
    except SystemExit as exc:
        print(f"⚠ No se pudo desempatar con Gemini ({exc}).")
        print(f"  Los {len(doubtful)} casos dudosos quedan SIN decidir; "
              "volverán a salir en un lote futuro.")
        return {}

    print(f"⚖  Desempatando {len(doubtful)} casos dudosos con Gemini…")
    resolved: dict[int, dict] = {}
    for n, _decision in doubtful:
        article = corpus.get(by_n[n]["id"])
        if article is None:
            continue
        time.sleep(rate_limit)
        _kept, info = is_real_article(chain, article.get("text") or "",
                                      model=model)
        if info is None:
            print(f"    [{n}] sin respuesta de Gemini — queda sin decidir")
            continue
        resolved[n] = {
            "category": info.get("category"),
            "confidence": info.get("confidence", 0.5),
            "text_issues": info.get("text_issues", []),
            "engine": "gemini-desempate",
            "reason": info.get("reason") or "desempate de Gemini",
        }
        print(f"    [{n}] {by_n[n].get('source', '?'):20} → {info.get('category')}")
    return resolved


def cmd_ingest(args: argparse.Namespace) -> None:
    manifest_path = BATCH_DIR / f"lote_{args.batch:03d}.manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"✗ No existe {manifest_path}. ¿Exportaste el lote?")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_n = {item["n"]: item for item in manifest["items"]}

    decisions, errors = parse_decisions(
        Path(args.decisions).read_text(encoding="utf-8"))
    if errors:
        print(f"⚠ {len(errors)} líneas ilegibles (se omiten):")
        for err in errors[:10]:
            print(f"    {err}")
        if len(errors) > 10:
            print(f"    … y {len(errors) - 10} más")
        print()

    unknown = sorted(set(decisions) - set(by_n))
    if unknown:
        print(f"⚠ {len(unknown)} decisiones no corresponden a este lote: "
              f"{unknown[:8]}")
        for n in unknown:
            decisions.pop(n)

    missing = sorted(set(by_n) - set(decisions))
    if missing and not args.partial:
        raise SystemExit(
            f"✗ Faltan {len(missing)} de {len(by_n)} decisiones "
            f"(p. ej. {missing[:8]}).\n"
            "  Complétalas, o usa --partial para ingerir solo las presentes."
        )

    # El text_head se toma del corpus, no de lo que escriba el agente: es lo
    # que entrena al prefilter y debe coincidir con la entrada real.
    corpus = {a.get("id"): a for a in load_corpus(Path(manifest["input"]))}

    doubtful = [(n, d) for n, d in sorted(decisions.items())
                if d["category"] == DOUBT_TOKEN]
    resolved: dict[int, dict] = {}
    if doubtful and not args.no_escalate:
        resolved = resolve_doubts(doubtful, corpus, by_n, args.model,
                                  args.rate_limit)
    for n, _ in doubtful:
        if n in resolved:
            decisions[n] = resolved[n]
        else:
            # Sin desempate no se inventa una categoría: el artículo se queda
            # fuera del log y reaparecerá en un lote futuro.
            decisions.pop(n)

    log_path = LOGS_DIR / "filter_decisions.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    written = 0
    with open(log_path, "a", encoding="utf-8") as flog:
        for n in sorted(decisions):
            item = by_n[n]
            article = corpus.get(item["id"])
            if article is None:
                counts["sin_articulo"] += 1
                continue
            decision = decisions[n]
            blocking = sorted(set(decision["text_issues"]) & BLOCKING_TEXT_ISSUES)
            category = "garbage" if blocking else decision["category"]
            kept = category == "political_article"
            flog.write(json.dumps({
                "id": item["id"],
                "url": item.get("url"),
                "source": item.get("source"),
                "engine": decision.get("engine", args.engine),
                "category": category,
                "confidence": decision["confidence"],
                "reason": (f"descartado por {', '.join(blocking)}" if blocking
                           else decision.get(
                               "reason", f"clasificado por {args.engine}")),
                "kept": kept,
                "escalated": False,
                "text_issues": decision["text_issues"],
                "text_head": (article.get("text") or "")[:_LOG_HEAD_CHARS],
                "batch": args.batch,
            }, ensure_ascii=False) + "\n")
            written += 1
            counts[category] += 1

    kept = counts["political_article"]
    print(f"✓ {written:,} decisiones → {log_path}  (engine={args.engine})")
    print(f"  conservados: {kept:,}   descartados: {written - kept:,}")
    for category, n in counts.most_common():
        if category != "sin_articulo":
            print(f"    {category:24} {n:,}")
    if counts["sin_articulo"]:
        print(f"  ⚠ {counts['sin_articulo']} ids del manifiesto ya no están "
              "en el corpus de entrada")

    # El cursor solo avanza cuando el lote está ingerido: si la sesión se
    # corta a mitad, el siguiente `next` vuelve a entregar estos artículos en
    # vez de saltárselos.
    input_path = Path(manifest["input"])
    state = read_state(input_path)
    if state.get("pending_batch") == args.batch:
        lines = [item["line"] for item in manifest["items"]
                 if item.get("line") is not None]
        if lines:
            state["cursor"] = max(state["cursor"], max(lines) + 1)
        state["pending_batch"] = None
        write_state(state)
        print(f"  cursor → línea {state['cursor']:,}")

    if resolved:
        print(f"  ⚖ {len(resolved)} resueltos por Gemini (desempate)")
    unresolved = len(doubtful) - len(resolved)
    if unresolved:
        print(f"  ⚠ {unresolved} dudas sin resolver: reaparecerán en un lote futuro")

    # Los archivos del lote son andamiaje: una vez ingerido, todo lo que
    # importa (categoría, confianza, razón, text_head, lote) vive en el log
    # de decisiones. Dejarlos acumularía ~2.500 archivos sueltos.
    if not args.keep_batch:
        removed = 0
        for path in (BATCH_DIR / f"lote_{args.batch:03d}.txt",
                     manifest_path,
                     Path(args.decisions)):
            try:
                path.unlink()
                removed += 1
            except OSError:
                pass
        if removed:
            print(f"  limpieza: {removed} archivos de trabajo del lote {args.batch}")

    if not args.no_build:
        kept_total = build_corpus(Path(manifest["input"]), verbose=False)
        print(f"  corpus → {kept_total:,} artículos en data/raw/articles.jsonl")

    total = len(decided_ids(log_path))
    print(f"\n  Decisiones acumuladas en el log: {total:,}")
    if total >= 2000:
        print("  → suficientes para entrenar el prefilter:")
        print("      .venv/bin/python scripts/train_prefilter.py")
    else:
        print(f"  → faltan ~{2000 - total:,} para entrenar el prefilter con "
              "holgura (2.000)")


def latest_decisions(log_path: Path,
                     prefer_engine: str | None = None) -> dict[str, dict]:
    """Decisión vigente por artículo.

    Por defecto gana la más reciente del log. Con `prefer_engine`, ese motor
    manda sobre los demás: sin una regla declarada, qué entra al corpus
    dependería del orden en que se corrieron los scripts, y el corpus dejaría
    de ser reproducible.
    """
    latest: dict[str, dict] = {}
    if not log_path.exists():
        return latest
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            article_id = entry.get("id")
            if not article_id:
                continue
            previous = latest.get(article_id)
            if previous is not None and prefer_engine:
                if previous.get("engine") == prefer_engine:
                    continue
                if entry.get("engine") != prefer_engine and \
                        previous.get("engine") == prefer_engine:
                    continue
            latest[article_id] = entry
    return latest


def cmd_build(args: argparse.Namespace) -> None:
    build_corpus(Path(args.input) if args.input else None,
                 Path(args.output) if args.output else None,
                 args.prefer_engine, verbose=True)


def build_corpus(input_path: Path | None = None, output_path: Path | None = None,
                 prefer_engine: str | None = "claude-agent",
                 verbose: bool = True) -> int:
    """Materializa el corpus filtrado: UN archivo con lo que se conserva.

    Se reconstruye entero cada vez a partir del log de decisiones, en vez de
    ir añadiendo al final. Es idempotente: correrlo dos veces da el mismo
    archivo, y una decisión corregida se refleja sin dejar el artículo viejo
    dentro. A esta escala reescribir cuesta segundos, y a cambio el archivo
    nunca queda a medias ni duplicado.
    """
    input_path = input_path or RAW_DIR / "articles_unfiltered.jsonl"
    output_path = output_path or RAW_DIR / "articles.jsonl"
    if not input_path.exists():
        raise SystemExit(f"✗ No existe {input_path}")

    decisions = latest_decisions(LOGS_DIR / "filter_decisions.jsonl",
                                 prefer_engine)
    if not decisions:
        raise SystemExit("✗ No hay decisiones todavía en logs/filter_decisions.jsonl")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: si esto se corta a la mitad, el archivo bueno sigue
    # intacto en vez de quedar truncado.
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    kept = 0
    undecided = 0
    by_engine: Counter = Counter()
    with open(input_path, encoding="utf-8") as fin, \
         open(tmp_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            try:
                article = json.loads(line)
            except json.JSONDecodeError:
                continue
            decision = decisions.get(article.get("id"))
            if decision is None:
                undecided += 1
                continue
            if decision.get("kept"):
                article.pop("_line", None)
                fout.write(json.dumps(article, ensure_ascii=False) + "\n")
                kept += 1
                by_engine[decision.get("engine", "?")] += 1
    tmp_path.replace(output_path)

    decided = len(decisions)
    if verbose:
        print(f"✓ {kept:,} artículos → {output_path}")
        print(f"  de {decided:,} decididos "
              f"({100 * kept / decided:.1f}% conservado)"
              f"  ·  {undecided:,} aún sin decidir")
        for engine, n in by_engine.most_common():
            print(f"    {engine:24} {n:,}")
    return kept


def cmd_compare(args: argparse.Namespace) -> None:
    """Concordancia entre dos motores sobre los artículos que ambos vieron."""
    log_path = LOGS_DIR / "filter_decisions.jsonl"
    if not log_path.exists():
        raise SystemExit(f"✗ No existe {log_path}")

    # Una decisión por (motor, id): si un motor repitió un artículo, vale la
    # última, que es la que refleja el criterio vigente.
    by_engine: dict[str, dict[str, str]] = defaultdict(dict)
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            engine = entry.get("engine")
            if entry.get("id") and engine:
                by_engine[engine][entry["id"]] = entry.get("category", "?")

    if args.a not in by_engine or args.b not in by_engine:
        raise SystemExit(
            f"✗ Motores en el log: {', '.join(sorted(by_engine)) or '(ninguno)'}\n"
            f"  Pediste '{args.a}' y '{args.b}'."
        )

    shared = sorted(set(by_engine[args.a]) & set(by_engine[args.b]))
    if not shared:
        raise SystemExit(
            f"✗ '{args.a}' y '{args.b}' no comparten ningún artículo.\n"
            f"  Genera el solape:  python scripts/agent_filter.py export "
            f"--overlap-with {args.b} --limit 200"
        )

    units_cat = [[by_engine[args.a][i], by_engine[args.b][i]] for i in shared]
    # La decisión que de verdad importa es binaria: entra o no entra al corpus.
    units_bin = [[c == "political_article" for c in pair] for pair in units_cat]

    alpha_cat = krippendorff_alpha(units_cat, level="nominal")
    alpha_bin = krippendorff_alpha(units_bin, level="nominal")
    pct_cat = percent_agreement(units_cat)
    pct_bin = percent_agreement(units_bin)

    print("=" * 66)
    print(f"  CONCORDANCIA  {args.a}  vs  {args.b}")
    print(f"  Artículos que ambos clasificaron: {len(shared):,}")
    print("=" * 66)
    print(f"\n  Categoría (5 clases)   α = {alpha_cat:.3f}"
          f"   acuerdo simple = {pct_cat:.1%}")
    print(f"  Conservar sí/no        α = {alpha_bin:.3f}"
          f"   acuerdo simple = {pct_bin:.1%}")
    threshold = 0.8
    verdict = ("≥ 0.8: los dos motores son intercambiables sobre este corpus"
               if (alpha_bin or 0) >= threshold else
               "< 0.8: NO son intercambiables — filtrar el corpus a medias "
               "entre ambos mezclaría dos criterios")
    print(f"\n  {verdict}")

    print("\n  Desacuerdos por par de categorías:")
    disagreements = Counter(
        (pair[0], pair[1]) for pair in units_cat if pair[0] != pair[1])
    if not disagreements:
        print("    (ninguno)")
    for (cat_a, cat_b), n in disagreements.most_common(12):
        print(f"    {args.a}={cat_a:22} {args.b}={cat_b:22} {n:4}")

    if args.export:
        out = Path(args.export)
        with open(out, "w", encoding="utf-8") as f:
            for i in shared:
                if by_engine[args.a][i] != by_engine[args.b][i]:
                    f.write(json.dumps({
                        "id": i, args.a: by_engine[args.a][i],
                        args.b: by_engine[args.b][i],
                    }, ensure_ascii=False) + "\n")
        print(f"\n  Desacuerdos detallados → {out}")
    print("=" * 66)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filtrado por el agente de Claude Code (sin API)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_export = sub.add_parser("export", help="Sacar un lote para el agente")
    p_export.add_argument("--limit", type=int, default=400)
    p_export.add_argument("--input", type=str, default=None)
    p_export.add_argument("--batch", type=int, default=None)
    p_export.add_argument("--seed", type=int, default=42)
    p_export.add_argument("--overlap-with", type=str, default=None,
                          help="Muestrear solo artículos que YA decidió este "
                               "motor (para medir concordancia)")
    p_export.add_argument("--allow-redo", action="store_true",
                          help="No excluir los que ya tienen decisión")
    p_export.set_defaults(func=cmd_export)

    p_ingest = sub.add_parser("ingest", help="Volcar las decisiones al log")
    p_ingest.add_argument("--batch", type=int, required=True)
    p_ingest.add_argument("--decisions", type=str, required=True)
    p_ingest.add_argument("--engine", type=str, default="claude-agent")
    p_ingest.add_argument("--partial", action="store_true",
                          help="Aceptar un lote incompleto")
    p_ingest.add_argument("--no-escalate", action="store_true",
                          help="No desempatar los 'dud' con Gemini")
    p_ingest.add_argument("--model", type=str, default="gemini-2.5-flash",
                          help="Modelo del desempate (default: el bueno, "
                               "que para eso son pocos casos)")
    p_ingest.add_argument("--rate-limit", type=float, default=4.5)
    p_ingest.add_argument("--keep-batch", action="store_true",
                          help="Conservar lote_NNN.txt, su manifiesto y el "
                               "archivo de decisiones tras ingerir")
    p_ingest.add_argument("--no-build", action="store_true",
                          help="No regenerar data/raw/articles.jsonl al ingerir")
    p_ingest.set_defaults(func=cmd_ingest)

    p_next = sub.add_parser("next", help="Siguiente lote de la travesía completa")
    p_next.add_argument("--size", type=int, default=60)
    p_next.add_argument("--input", type=str, default=None)
    p_next.add_argument("--budget", type=int, default=None,
                        help=f"Tokens de texto por tanda (default: "
                             f"{DEFAULT_BUDGET_TOKENS:,})")
    p_next.add_argument("--reset-session", action="store_true",
                        help="Empieza una tanda nueva (pon esto al abrir sesión)")
    p_next.add_argument("--force", action="store_true",
                        help="Rehacer el lote pendiente")
    p_next.set_defaults(func=cmd_next)

    p_status = sub.add_parser("status", help="Progreso de la travesía")
    p_status.add_argument("--input", type=str, default=None)
    p_status.add_argument("--json", action="store_true",
                          help="Salida legible por máquina (para el servicio)")
    p_status.set_defaults(func=cmd_status)

    p_build = sub.add_parser(
        "build", help="Materializa el corpus filtrado en UN archivo")
    p_build.add_argument("--input", type=str, default=None)
    p_build.add_argument("--output", type=str, default=None,
                         help="default: data/raw/articles.jsonl")
    p_build.add_argument("--prefer-engine", type=str, default="claude-agent",
                         help="Motor que manda si varios decidieron el mismo "
                              "artículo (default: claude-agent). Vacío = gana "
                              "la decisión más reciente")
    p_build.set_defaults(func=cmd_build)

    p_cmp = sub.add_parser("compare", help="Concordancia entre dos motores")
    p_cmp.add_argument("--a", type=str, default="claude-agent")
    p_cmp.add_argument("--b", type=str, default="llm")
    p_cmp.add_argument("--export", type=str, default=None,
                       help="JSONL con los desacuerdos, para revisarlos")
    p_cmp.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
