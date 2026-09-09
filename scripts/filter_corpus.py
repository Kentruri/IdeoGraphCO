"""Filtra un corpus YA recolectado: politicidad + colombianidad + limpieza.

Permite separar las dos fases que consumen recursos distintos:

  1. Recolectar sin API   → `collect_corpus.py --no-filter` (red, horas)
  2. Filtrar aparte       → este script (API de Gemini, reanudable)

Ventaja sobre filtrar en línea: con el corpus ya en disco puedes filtrar una
MUESTRA con el LLM, entrenar el prefilter con esas decisiones, y dejar que el
modelo local resuelva la mayor parte del resto — bajando muchísimo el gasto
de API. Filtrando en línea el prefilter llega tarde.

Reanudable: cursor sidecar (`<salida>.cursor`) y cortacircuitos de cuota. Si
se agotan los créditos se detiene SIN avanzar el cursor y al relanzarlo
continúa en el mismo artículo.

Uso:
    # todo el corpus
    python scripts/filter_corpus.py

    # una muestra primero, para entrenar el prefilter con sus decisiones
    python scripts/filter_corpus.py --limit 2500
    python scripts/train_prefilter.py
    python scripts/filter_corpus.py --prefilter        # el resto, ya barato

    # rutas explícitas
    python scripts/filter_corpus.py --input data/raw/articles_unfiltered.jsonl \\
        --output data/raw/articles.jsonl
"""

import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.paths import LOGS_DIR, RAW_DIR  # noqa: E402
from src.scraper.article_filter import is_real_article  # noqa: E402
from src.scraper.llm_providers import build_provider_chain  # noqa: E402
from src.scraper.prefilter import try_load_prefilter  # noqa: E402

logger = logging.getLogger("filter_corpus")

_TEXT_HEAD_CHARS = 3000
_MAX_CONSECUTIVE_FAILURES = 5


def _cursor_path(output_path: Path) -> Path:
    return Path(str(output_path) + ".cursor")


def _read_cursor(output_path: Path) -> int:
    path = _cursor_path(output_path)
    return int(path.read_text().strip()) if path.exists() else 0


def _write_cursor(output_path: Path, line_num: int) -> None:
    _cursor_path(output_path).write_text(str(line_num))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filtra un corpus ya recolectado (politicidad + colombianidad)",
    )
    parser.add_argument("--input", type=str, default=None,
                        help="JSONL sin filtrar (default: data/raw/articles_unfiltered.jsonl)")
    parser.add_argument("--output", type=str, default=None,
                        help="JSONL filtrado (default: data/raw/articles.jsonl)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Procesar solo N artículos en esta corrida "
                             "(útil para filtrar una muestra y entrenar el prefilter)")
    parser.add_argument("--provider", type=str, default="gemini",
                        help="Proveedor(es) en orden de relevo. 'gemini', "
                             "'claude', o 'gemini,claude' para que Claude "
                             "tome el relevo cuando Gemini se quede sin cuota")
    parser.add_argument("--model", type=str, default=None,
                        help="Modelo primario (default: el del proveedor)")
    parser.add_argument("--escalate-model", type=str, default=None)
    parser.add_argument("--no-escalate", action="store_true")
    parser.add_argument("--escalate-threshold", type=float, default=0.7)
    parser.add_argument("--rate-limit", type=float, default=None,
                        help="Segundos entre llamadas. Por defecto lo fija el "
                             "proveedor activo (Gemini free tier: 4.5s)")
    parser.add_argument("--filter-log", type=str, default=None,
                        help="JSONL de decisiones (default: logs/filter_decisions.jsonl)")
    parser.add_argument("--no-reuse", action="store_true",
                        help="No reutilizar decisiones ya presentes en el log "
                             "(por defecto se reutilizan y no se re-pagan)")
    parser.add_argument("--prefer-engine", type=str, default=None,
                        help="Motor que MANDA cuando varios decidieron el "
                             "mismo artículo (p. ej. 'claude-agent'). Sin "
                             "esto gana la decisión más reciente del log")
    parser.add_argument("--prefilter", nargs="?", const="__default__", default=None,
                        help="Usa el prefilter local para resolver gratis lo obvio")
    parser.add_argument("--force", action="store_true",
                        help="Re-filtrar desde cero (trunca la salida y el cursor)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # El SDK de Gemini y httpx loguean cada petición: ensucia la barra de tqdm.
    for noisy in ("google_genai", "google_genai.types", "httpx", "httpcore",
                  "google.genai", "google.genai.models"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    input_path = Path(args.input) if args.input else RAW_DIR / "articles_unfiltered.jsonl"
    output_path = Path(args.output) if args.output else RAW_DIR / "articles.jsonl"
    filter_log = (Path(args.filter_log) if args.filter_log
                  else LOGS_DIR / "filter_decisions.jsonl")

    if not input_path.exists():
        raise SystemExit(
            f"✗ No existe {input_path}\n"
            "  Recolecta primero sin filtro:\n"
            "    python scripts/collect_corpus.py --no-filter --target 49000"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    filter_log.parent.mkdir(parents=True, exist_ok=True)

    from dotenv import load_dotenv

    load_dotenv()
    order = [name.strip() for name in args.provider.split(",") if name.strip()]
    chain = build_provider_chain(
        order,
        models={name: args.model for name in order} if args.model else None,
        escalate_models=({name: args.escalate_model for name in order}
                         if args.escalate_model else None),
        intervals=({name: args.rate_limit for name in order}
                   if args.rate_limit is not None else None),
    )

    prefilter = None
    if args.prefilter:
        path = ("data/models/prefilter.joblib" if args.prefilter == "__default__"
                else args.prefilter)
        prefilter = try_load_prefilter(path)

    if args.force:
        _write_cursor(output_path, 0)
        cursor = 0
        mode = "w"
    else:
        cursor = _read_cursor(output_path)
        mode = "a"
        if output_path.exists() and output_path.stat().st_size > 0 and cursor == 0:
            raise SystemExit(
                f"✗ {output_path} ya tiene contenido pero el cursor está en 0.\n"
                "  Appendear duplicaría artículos. Usa --force para re-filtrar."
            )

    # Decisiones ya tomadas (por Gemini en una corrida anterior, por el
    # agente vía scripts/agent_filter.py, o por quien sea): se reutilizan en
    # vez de volver a pagarlas. Es lo que permite que el agente aporte al
    # mismo corpus sin duplicar llamadas ni criterios.
    reused: dict[str, dict] = {}
    if not args.no_reuse and filter_log.exists():
        with open(filter_log, encoding="utf-8") as f:
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
                previous = reused.get(article_id)
                if previous is None:
                    reused[article_id] = entry
                    continue
                # Dos motores decidieron el mismo artículo. Sin una regla
                # explícita ganaba "el último del log", que depende del orden
                # en que se corrieron los scripts: el corpus dejaría de ser
                # reproducible. Con --prefer-engine la precedencia es una
                # decisión metodológica declarada, no un accidente.
                if args.prefer_engine:
                    if previous.get("engine") == args.prefer_engine:
                        continue
                    if entry.get("engine") == args.prefer_engine:
                        reused[article_id] = entry
                        continue
                reused[article_id] = entry

    with open(input_path, encoding="utf-8") as f:
        total_lines = sum(1 for line in f if line.strip())

    pending = total_lines - cursor
    if args.limit is not None:
        pending = min(pending, args.limit)

    print("=" * 66)
    print("  FILTRADO DEL CORPUS")
    print(f"  Entrada:    {input_path.name} ({total_lines:,} artículos)")
    print(f"  Ya filtrados: {cursor:,}")
    print(f"  En esta corrida: {pending:,}")
    print(f"  Prefilter:  {'SÍ' if prefilter else 'NO'}")
    print("  Proveedores: " + " → ".join(
        f"{p.name}({p.model})" for p in chain.providers))
    print(f"  Decisiones reutilizables: {len(reused):,}")
    if reused:
        engines = Counter(e.get("engine", "?") for e in reused.values())
        print("    por motor: " + ", ".join(
            f"{name} {n:,}" for name, n in engines.most_common()))
    if args.prefer_engine:
        print(f"  Motor con precedencia: {args.prefer_engine}")
    print("=" * 66)
    print()

    if pending <= 0:
        print("✓ Nada pendiente. Corpus filtrado completo.")
        return

    from tqdm import tqdm

    counts: Counter = Counter()
    processed = 0
    consecutive_failures = 0
    started = time.time()
    # Con una cadena, "auto" significa «usa el modelo de escalada que
    # cada proveedor declara»; el nombre concreto lo resuelve la cadena.
    escalate = None if args.no_escalate else (args.escalate_model or "auto")

    pbar = tqdm(total=pending, desc="Filtrando", unit="art", smoothing=0.1)
    try:
        with open(input_path, encoding="utf-8") as fin, \
             open(output_path, mode, encoding="utf-8") as fout, \
             open(filter_log, "a", encoding="utf-8") as flog:

            for i, line in enumerate(fin):
                if i < cursor:
                    continue
                if args.limit is not None and processed >= args.limit:
                    break
                line = line.strip()
                if not line:
                    continue

                try:
                    article = json.loads(line)
                    text = article["text"]
                except (json.JSONDecodeError, KeyError) as exc:
                    logger.warning("Línea %d corrupta (%s), saltando.", i + 1, exc)
                    counts["corrupta"] += 1
                    _write_cursor(output_path, i + 1)
                    processed += 1
                    pbar.update(1)
                    continue

                engine = "llm"
                info: dict | None = None
                is_political = False

                # Etapa 0: decisión ya tomada antes (agente, o corrida previa)
                previous = reused.get(article.get("id"))
                if previous is not None:
                    engine = previous.get("engine", "reutilizada")
                    is_political = bool(previous.get("kept"))
                    info = {
                        "category": previous.get("category"),
                        "confidence": previous.get("confidence"),
                        "reason": previous.get("reason"),
                        "text_issues": previous.get("text_issues", []),
                        "provider": previous.get("provider"),
                        "reused": True,
                    }
                    counts["reutilizadas"] += 1

                # Etapa 1: prefilter local (gratis)
                if info is None and prefilter is not None:
                    decision = prefilter.decide(text[:_TEXT_HEAD_CHARS])
                    if decision.action != "uncertain":
                        engine = "prefilter"
                        is_political = decision.action == "keep"
                        info = {
                            "category": ("political_article" if is_political
                                         else "nonpolitical_article"),
                            "confidence": round(decision.probability, 4),
                            "reason": f"prefilter p={decision.probability:.3f}",
                            "text_issues": [],
                        }

                # Etapa 2: filter LLM (zona gris o sin prefilter)
                if info is None:
                    # El ritmo lo marca el proveedor ACTIVO: al relevar a uno
                    # con límites más holgados, la espera se ajusta sola en
                    # vez de arrastrar el 4.5s del plan gratuito de Gemini.
                    time.sleep(chain.min_interval())
                    is_political, info = is_real_article(
                        chain, text,
                        escalate_model=escalate,
                        escalate_threshold=args.escalate_threshold,
                    )
                    if info is None:
                        if chain.active() is None:
                            print("\n\n⚠ Todos los proveedores agotaron su "
                                  f"cuota ({', '.join(chain.exhausted())}).")
                            print(f"  El cursor queda en {i}: relanza el mismo "
                                  "comando cuando se restablezca, o añade un "
                                  "proveedor con --provider gemini,claude.")
                            break
                        consecutive_failures += 1
                        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                            print(f"\n\n⚠ {consecutive_failures} fallos consecutivos "
                                  "del LLM.")
                            print(f"  El cursor queda en {i}: relanza el mismo "
                                  "comando cuando se restablezca.")
                            break
                        counts["filter_error"] += 1
                        _write_cursor(output_path, i + 1)
                        processed += 1
                        pbar.update(1)
                        continue
                    consecutive_failures = 0

                if not info.get("reused"):
                    flog.write(json.dumps({
                        "id": article.get("id"),
                        "url": article.get("url"),
                        "source": article.get("source"),
                        "engine": engine,
                        "provider": info.get("provider"),
                        "category": info.get("category"),
                        "confidence": info.get("confidence"),
                        "reason": info.get("reason"),
                        "kept": is_political,
                        "escalated": info.get("escalated", False),
                        "text_issues": info.get("text_issues", []),
                        "text_head": text[:_TEXT_HEAD_CHARS],
                    }, ensure_ascii=False) + "\n")
                    flog.flush()

                if is_political:
                    fout.write(json.dumps(article, ensure_ascii=False) + "\n")
                    fout.flush()
                    counts[f"kept_{engine}"] += 1
                else:
                    counts[f"drop:{info.get('category', '?')}"] += 1
                for issue in info.get("text_issues", []):
                    counts[f"issue:{issue}"] += 1

                _write_cursor(output_path, i + 1)
                processed += 1
                pbar.update(1)
                pbar.set_postfix(
                    keep=sum(v for k, v in counts.items()
                             if k.startswith("kept_")),
                    drop=sum(v for k, v in counts.items() if k.startswith("drop:")),
                )
    except KeyboardInterrupt:
        print("\n\n⏸  Interrumpido. El cursor quedó guardado.")
    finally:
        pbar.close()

    kept_by_engine = {k[len("kept_"):]: v for k, v in counts.items()
                      if k.startswith("kept_")}
    kept = sum(kept_by_engine.values())
    dropped = sum(v for k, v in counts.items() if k.startswith("drop:"))
    print()
    print("=" * 66)
    print(f"  Procesados:  {processed:,} en {time.time() - started:.0f}s")
    print(f"  ✓ Conservados: {kept:,}")
    for name, n in sorted(kept_by_engine.items(), key=lambda kv: -kv[1]):
        print(f"      por {name:22} {n:,}")
    if counts["reutilizadas"]:
        print(f"  ♻ Reutilizadas: {counts['reutilizadas']:,} "
              "(decididas antes; no costaron API)")
    if chain.exhausted():
        print(f"  ⚠ Proveedores agotados: {', '.join(chain.exhausted())}")
    print(f"  ⊘ Descartados: {dropped:,}")
    for key in sorted(k for k in counts if k.startswith("drop:")):
        print(f"      {key[5:]:24} {counts[key]:,}")
    issues = sorted(k for k in counts if k.startswith("issue:"))
    if issues:
        print("  Problemas de texto detectados:")
        for key in issues:
            print(f"      {key[6:]:24} {counts[key]:,}")
    if counts["filter_error"]:
        print(f"  ⚠ Errores del filtro: {counts['filter_error']:,} (se reintentan)")
    print(f"  Salida: {output_path}")

    remaining = total_lines - _read_cursor(output_path)
    if remaining > 0:
        print(f"\n  Faltan {remaining:,}. Continuar con el mismo comando.")
    else:
        print("\n  ✓ Corpus filtrado completo. Siguiente paso:")
        print("      python scripts/label.py     # etiquetado silver")
    print("=" * 66)


if __name__ == "__main__":
    main()
