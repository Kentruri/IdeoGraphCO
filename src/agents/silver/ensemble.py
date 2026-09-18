"""Etiquetado silver por ensemble: varios jueces por artículo + consenso.

Escribe dos archivos:

- el SILVER (`data/silver/silver_set.jsonl` por defecto): un registro por
  artículo con `label`, `label_idx`, `label_source="silver-ensemble"` y el
  bloque `consensus` (status, accepted, agreement, votos). Compatible con lo
  que ya consumen `prepare_splits.py` y el Dataset.
- los VEREDICTOS (`<silver>.verdicts.jsonl`): lo que dijo CADA juez de cada
  artículo. Es la trazabilidad del silver y lo que `calibration.py` necesita
  para medir si el acuerdo predice el acierto. Sin este archivo el consenso
  sería una caja negra.

Reanudable con cursor sidecar, igual que el juez simple. Un juez que agota
cuota se retira del resto de la corrida (con aviso); si no queda ninguno, la
corrida para SIN avanzar el cursor y se retoma después.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.agents.silver.consensus import SIN_VEREDICTO, mean_scores, resolve
from src.agents.silver.judges import Judge, Verdict
from src.core.ids import article_id
from src.core.paths import RAW_DIR, SILVER_DIR
from src.core.schema import CLASS_TO_IDX

logger = logging.getLogger(__name__)

LABEL_SOURCE = "silver-ensemble"

# Artículos seguidos en los que NINGÚN juez emite veredicto antes de parar.
# Un fallo aislado se anota y se sigue; una racha así es cuota o servicio
# caído, y seguir solo llenaría el .failed.
_MAX_CONSECUTIVE_FAILURES = 5


def _cursor_path(output_path: Path) -> Path:
    return Path(str(output_path) + ".cursor")


def read_cursor(output_path: Path) -> int:
    p = _cursor_path(output_path)
    return int(p.read_text().strip()) if p.exists() else 0


def write_cursor(output_path: Path, line_num: int) -> None:
    _cursor_path(output_path).write_text(str(line_num))


def verdicts_path_for(output_path: Path) -> Path:
    return output_path.with_name(output_path.stem + ".verdicts.jsonl")


def _append_failed(output_path: Path, line_num: int, aid: str, reason: str) -> None:
    with open(str(output_path) + ".failed", "a", encoding="utf-8") as f:
        f.write(json.dumps({"line": line_num, "id": aid, "reason": reason}) + "\n")


def judge_article(judges: list[Judge], title: str | None, text: str) -> list[Verdict]:
    """Todos los jueces ven el mismo artículo, en paralelo.

    Son proveedores distintos con límites distintos, así que no compiten
    entre sí; cada juez espacia sus propias llamadas.
    """
    if len(judges) == 1:
        return [judges[0].judge(title, text)]
    with ThreadPoolExecutor(max_workers=len(judges)) as pool:
        return list(pool.map(lambda j: j.judge(title, text), judges))


def build_record(raw: dict, verdicts: list[Verdict], rule: str) -> tuple[dict, dict]:
    """(registro silver, registro de veredictos) para un artículo."""
    consensus = resolve(verdicts, rule)
    record_id = raw.get("id") or article_id(raw.get("url", ""))

    verdict_record = {
        "id": record_id,
        "rule": rule,
        "consensus": consensus.to_dict(),
        "verdicts": [v.to_dict() for v in verdicts],
    }

    silver_record = None
    if consensus.label is not None:
        silver_record = {
            "id": record_id,
            "text": raw["text"],
            "title": raw.get("title", ""),
            "source": raw.get("source", ""),
            "category": raw.get("category", ""),
            "url": raw.get("url", ""),
            "date": raw.get("date"),
            "label": consensus.label,
            "label_idx": CLASS_TO_IDX[consensus.label],
            "label_source": LABEL_SOURCE,
            "judge_models": [v.model for v in verdicts if v.ok],
            "judge_truncated": any(v.truncated for v in verdicts),
            "consensus": consensus.to_dict(),
            **mean_scores(verdicts),
        }
    return silver_record, verdict_record


def label_with_ensemble(
    judges: list[Judge],
    input_path: Path | None = None,
    output_path: Path | None = None,
    rule: str = "majority",
    exclude_ids: set[str] | None = None,
    max_articles: int | None = None,
    force: bool = False,
    progress: bool = True,
) -> dict:
    """Etiqueta `input_path` con el ensemble. Devuelve un resumen."""
    input_path = input_path or RAW_DIR / "articles.jsonl"
    output_path = output_path or SILVER_DIR / "silver_set.jsonl"
    verdicts_path = verdicts_path_for(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    exclude_ids = exclude_ids or set()

    if force:
        write_cursor(output_path, 0)
        cursor, mode = 0, "w"
    else:
        cursor, mode = read_cursor(output_path), "a"
        if output_path.exists() and output_path.stat().st_size > 0 and cursor == 0:
            raise SystemExit(
                f"{output_path} tiene contenido pero el cursor está en 0: "
                "appendear duplicaría artículos. Usa --force para rehacer."
            )

    with open(input_path, encoding="utf-8") as f:
        total_lines = sum(1 for line in f if line.strip())
    pending = total_lines - cursor
    if max_articles is not None:
        pending = min(pending, max_articles)

    active = list(judges)
    counts = {"labeled": 0, "accepted": 0, "excluded": 0, "failed": 0,
              "status": {}, "retired_judges": []}
    if pending <= 0:
        return {**counts, "cursor": cursor, "total": total_lines}

    logger.info("Ensemble: %s · regla=%s · %d pendientes · %d excluidos (gold)",
                ", ".join(f"{j.name}({j.model})" for j in judges), rule,
                pending, len(exclude_ids))

    pbar = None
    if progress:
        from tqdm import tqdm

        pbar = tqdm(total=pending, desc="Ensemble", unit="art", smoothing=0.1)

    consecutive_failures = 0
    processed = 0
    try:
        with open(input_path, encoding="utf-8") as fin, \
             open(output_path, mode, encoding="utf-8") as fout, \
             open(verdicts_path, mode, encoding="utf-8") as fver:

            for i, line in enumerate(fin):
                if i < cursor:
                    continue
                if max_articles is not None and processed >= max_articles:
                    break
                line = line.strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                    raw["text"]
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    _append_failed(output_path, i + 1, "?", f"línea corrupta: {exc}")
                    counts["failed"] += 1
                    write_cursor(output_path, i + 1)
                    processed += 1
                    if pbar:
                        pbar.update(1)
                    continue

                aid = raw.get("id") or article_id(raw.get("url", ""))
                if aid in exclude_ids:
                    # El gold es el conjunto de prueba: fuera del silver.
                    counts["excluded"] += 1
                    write_cursor(output_path, i + 1)
                    processed += 1
                    if pbar:
                        pbar.update(1)
                    continue

                verdicts = judge_article(active, raw.get("title"), raw["text"])

                # Un juez sin cuota se retira: seguir preguntándole solo
                # quema tiempo en reintentos. Los siguientes consensos serán
                # con menos jueces, y `n_judges` lo deja registrado.
                for v in verdicts:
                    if v.quota:
                        active = [j for j in active if j.name != v.judge]
                        counts["retired_judges"].append(v.judge)
                        logger.error("Juez '%s' sin cuota: retirado del resto "
                                     "de la corrida. Quedan: %s", v.judge,
                                     [j.name for j in active] or "NINGUNO")
                if not active:
                    logger.error("Ningún juez con cuota. Cursor en %d; relanza "
                                 "cuando se renueve.", i)
                    break

                silver_record, verdict_record = build_record(raw, verdicts, rule)
                status = verdict_record["consensus"]["status"]

                if status == SIN_VEREDICTO:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        logger.error("%d artículos seguidos sin ningún veredicto: "
                                     "paro sin avanzar el cursor (línea %d).",
                                     consecutive_failures, i)
                        break
                    _append_failed(output_path, i + 1, aid, "sin veredicto")
                    counts["failed"] += 1
                else:
                    consecutive_failures = 0
                    fver.write(json.dumps(verdict_record, ensure_ascii=False) + "\n")
                    fver.flush()
                    if silver_record is not None:
                        fout.write(json.dumps(silver_record, ensure_ascii=False) + "\n")
                        fout.flush()
                        counts["labeled"] += 1
                        if silver_record["consensus"]["accepted"]:
                            counts["accepted"] += 1
                    counts["status"][status] = counts["status"].get(status, 0) + 1

                write_cursor(output_path, i + 1)
                processed += 1
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix(ok=counts["labeled"], acc=counts["accepted"])
    finally:
        if pbar:
            pbar.close()

    return {**counts, "cursor": read_cursor(output_path), "total": total_lines,
            "output": str(output_path), "verdicts": str(verdicts_path)}
