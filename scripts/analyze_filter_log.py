"""Analiza el log estructurado de decisiones del filter LLM.

Lee `logs/filter_decisions.jsonl` (generado por el scraper con --filter-log)
y muestra distribución de confidence, conteos por categoría y casos
sospechosos (baja confidence en keeps o alta confidence en drops dudosos).

Útil para decidir si vale la pena implementar un umbral de escalado
(re-procesar casos con `confidence < N` con un modelo más caro).

Uso:
    python scripts/analyze_filter_log.py
    python scripts/analyze_filter_log.py --log logs/filter_decisions.jsonl
    python scripts/analyze_filter_log.py --threshold 0.7
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def percentile(sorted_vals: list[float], pct: float) -> float:
    """Percentil sin numpy (sorted_vals debe estar ordenado)."""
    if not sorted_vals:
        return 0.0
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * pct)))
    return sorted_vals[idx]


def main() -> None:
    parser = argparse.ArgumentParser(description="Analiza log de decisiones del filter")
    parser.add_argument(
        "--log", type=str, default=None,
        help="JSONL del filter (default: logs/filter_decisions.jsonl)",
    )
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="Umbral de confidence considerado 'bajo' (default: 0.7)",
    )
    parser.add_argument(
        "--show-suspicious", type=int, default=5,
        help="Cuántos casos sospechosos mostrar (default: 5)",
    )
    args = parser.parse_args()

    from src.core.paths import LOGS_DIR

    log_path = Path(args.log) if args.log else LOGS_DIR / "filter_decisions.jsonl"
    if not log_path.exists():
        print(f"✗ No existe {log_path}.")
        print("  Corre primero el scraper con --filter-log (es el default).")
        return

    decisions: list[dict] = []
    n_prefilter_keep = 0
    n_prefilter_drop = 0
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # Las decisiones del prefilter se cuentan aparte: su "confidence"
            # es P(político) del modelo local — otra escala, invertida para
            # los drops — y mezclarla con la del LLM corrompía percentiles,
            # umbral de escalado y casos sospechosos.
            if record.get("engine") == "prefilter":
                if record.get("kept"):
                    n_prefilter_keep += 1
                else:
                    n_prefilter_drop += 1
                continue
            decisions.append(record)

    n_prefilter = n_prefilter_keep + n_prefilter_drop
    if n_prefilter:
        print(f"\n(prefilter local: {n_prefilter} decisiones — "
              f"{n_prefilter_keep} keep, {n_prefilter_drop} drop — "
              "excluidas del análisis de confidence del LLM)")

    if not decisions:
        print("Log vacío (sin decisiones del LLM).")
        return

    # --- Problemas de limpieza del texto reportados por el LLM ---
    issue_counts = Counter()
    for d in decisions:
        for issue in d.get("text_issues") or []:
            issue_counts[issue] += 1
    if issue_counts:
        print("\n=== Problemas de texto detectados por el filtro ===")
        for issue, n in issue_counts.most_common():
            tag = " (descarta)" if issue != "boilerplate_residual" else " (solo señal)"
            print(f"  {issue:22} {n:5}{tag}")
        n_boiler = issue_counts.get("boilerplate_residual", 0)
        if n_boiler:
            print(f"\n  → {n_boiler} artículos con restos de plantilla: revisa "
                  "src/scraper/cleaner.py. Ejemplos:")
            shown = 0
            for d in decisions:
                if "boilerplate_residual" in (d.get("text_issues") or []) and shown < 3:
                    print(f"     [{d.get('source','?')}] {d.get('url','')[:70]}")
                    shown += 1

    # --- Política extranjera: cuánto produce cada fuente ---
    foreign = [d for d in decisions if d.get("category") == "political_foreign"]
    if foreign:
        by_source = Counter(d.get("source", "?") for d in foreign)
        kept_by_source = Counter(d.get("source", "?") for d in decisions if d.get("kept"))
        print(f"\n=== Política EXTRANJERA descartada ({len(foreign)}) ===")
        print("  Fuentes que más contenido internacional producen:")
        for src, n in by_source.most_common(10):
            total_src = n + kept_by_source.get(src, 0)
            pct = 100 * n / total_src if total_src else 0
            print(f"    {src:22} {n:4} de {total_src:4} ({pct:.0f}% internacional)")
        print("  → Si una fuente supera ~50%, evalúa si vale la pena scrapearla:")
        print("    gastas API para descartar la mayoría de lo que trae.")

    total = len(decisions)
    n_kept = sum(1 for d in decisions if d.get("kept"))
    n_drop = total - n_kept
    n_escalated = sum(1 for d in decisions if d.get("escalated"))

    print(f"\n=== Filter log: {log_path} ===")
    print(f"Total decisiones: {total}")
    print(f"  ✓ Keep (political_article): {n_kept} ({100*n_kept/total:.1f}%)")
    print(f"  ✗ Drop (otras categorías):   {n_drop} ({100*n_drop/total:.1f}%)")
    if n_escalated > 0:
        print(f"  ↑ Escaladas a modelo grande: {n_escalated} "
              f"({100*n_escalated/total:.1f}%) — gasto extra de API")

    # --- Distribución de confidence global ---
    all_confs = sorted(
        d["confidence"] for d in decisions if isinstance(d.get("confidence"), (int, float))
    )
    if all_confs:
        print(f"\n=== Confidence global (n={len(all_confs)}) ===")
        print(f"  min:     {all_confs[0]:.3f}")
        print(f"  p25:     {percentile(all_confs, 0.25):.3f}")
        print(f"  mediana: {percentile(all_confs, 0.50):.3f}")
        print(f"  p75:     {percentile(all_confs, 0.75):.3f}")
        print(f"  max:     {all_confs[-1]:.3f}")
        print(f"  media:   {sum(all_confs)/len(all_confs):.3f}")

    # --- Confidence por decisión (keep vs drop) ---
    keep_confs = sorted(
        d["confidence"] for d in decisions
        if d.get("kept") and isinstance(d.get("confidence"), (int, float))
    )
    drop_confs = sorted(
        d["confidence"] for d in decisions
        if not d.get("kept") and isinstance(d.get("confidence"), (int, float))
    )

    if keep_confs:
        print(f"\n=== Confidence en KEEP (n={len(keep_confs)}) ===")
        print(f"  mediana: {percentile(keep_confs, 0.50):.3f}  "
              f"min: {keep_confs[0]:.3f}  max: {keep_confs[-1]:.3f}")
    if drop_confs:
        print(f"=== Confidence en DROP (n={len(drop_confs)}) ===")
        print(f"  mediana: {percentile(drop_confs, 0.50):.3f}  "
              f"min: {drop_confs[0]:.3f}  max: {drop_confs[-1]:.3f}")

    # --- Conteo por categoría ---
    by_cat = Counter(d.get("category", "?") for d in decisions)
    print("\n=== Por categoría ===")
    for cat, c in by_cat.most_common():
        print(f"  {cat:25} {c:5d}  ({100*c/total:5.1f}%)")

    # --- Confidence promedio por categoría ---
    cat_confs: dict[str, list[float]] = defaultdict(list)
    for d in decisions:
        if isinstance(d.get("confidence"), (int, float)):
            cat_confs[d.get("category", "?")].append(d["confidence"])
    print("\n=== Confidence media por categoría ===")
    for cat in sorted(cat_confs):
        cs = cat_confs[cat]
        print(f"  {cat:25} media={sum(cs)/len(cs):.3f}  "
              f"min={min(cs):.3f}  n={len(cs)}")

    # --- Casos sospechosos: baja confidence en KEEP ---
    threshold = args.threshold
    low_keeps = [d for d in decisions if d.get("kept") and isinstance(d.get("confidence"), (int, float)) and d["confidence"] < threshold]
    print(f"\n=== KEEPS con confidence < {threshold} ({len(low_keeps)} casos) ===")
    print("  → Estos artículos pasaron como políticos pero el LLM no estaba seguro.")
    print("  → Candidatos a re-procesar con modelo más caro.")
    if low_keeps:
        for d in sorted(low_keeps, key=lambda x: x["confidence"])[: args.show_suspicious]:
            print(f"  conf={d['confidence']:.2f}  [{d.get('source','?'):15}] {d.get('reason','')[:70]}")

    # --- Casos sospechosos: alta confidence en DROP — verifica si son falsos negativos ---
    high_drops = [d for d in decisions if not d.get("kept") and isinstance(d.get("confidence"), (int, float)) and d["confidence"] >= 0.95 and d.get("category") == "nonpolitical_article"]
    print(f"\n=== DROPS con confidence >= 0.95 en 'nonpolitical_article' ({len(high_drops)} casos) ===")
    print("  → El LLM está muy seguro de que NO son políticos.")
    print("  → Revisar 2-3 ejemplos para validar criterio del prompt.")
    if high_drops:
        for d in sorted(high_drops, key=lambda x: -x["confidence"])[: args.show_suspicious]:
            print(f"  conf={d['confidence']:.2f}  [{d.get('source','?'):15}] {d.get('reason','')[:70]}")

    # --- Veredicto sobre escalado ---
    print("\n=== ¿Vale la pena un umbral de escalado? ===")
    if all_confs:
        pct_below_threshold = 100 * sum(1 for c in all_confs if c < threshold) / len(all_confs)
        print(f"  Casos con confidence < {threshold}: {pct_below_threshold:.1f}%")
        if pct_below_threshold >= 5:
            print("  → SÍ. Hay suficientes casos dudosos para que un escalado")
            print("    a modelo más caro (gemini-2.5-flash o pro) sea útil.")
        elif pct_below_threshold >= 1:
            print("  → MARGINAL. Pocos casos dudosos, evalúa si el gasto extra")
            print("    se justifica para tu volumen total.")
        else:
            print("  → NO. El modelo está muy seguro casi siempre.")
            print("    Un escalado no aportaría mucha calidad.")


if __name__ == "__main__":
    main()
