#!/usr/bin/env python3
"""Orquesta la ronda r4 del silver: confirmar lo de un solo juez y balancear.

Qué juzga, en este orden de prioridad:

1. `decidir_p3`  — los artículos de la 3ª pasada donde haiku y sonnet
   discreparon y falta opus. Su voto decide; el de los demás ya está.
2. `confirmar`   — etiquetas de p1 en clases escasas que puso haiku SOLO. En
   p2/p3 su precisión contra la mayoría fue de 0,60-0,65 en populismo y
   doctrinarismo: ahí una etiqueta de un juez es casi una moneda al aire.
3. `candidatos`  — lo que minó `silver_mine.py` para las clases escasas.

La regla es la mayoría de tres, evaluada perezosa (ver `silver_estado.py`):
haiku y sonnet votan todo; opus solo donde ellos discrepan. Haiku y sonnet van
cada uno en dos agentes en paralelo, repartidos en ALTERNANCIA sobre la lista
priorizada (no uno por arriba y otro por abajo): así, si la cuota corta, lo que
queda sin juzgar es la cola menos prometedora y no el medio de la lista.

Este proceso no etiqueta: lanza `silver_runner.py` por juez y shard, le pasa a
opus lo que haiku y sonnet dejan empatado, y relanza a quien se caiga. Para al
llegar al tope semanal o cuando no queda nada pendiente.

    python scripts/silver_ronda.py preparar --plan data/silver/plan_r4.json
    python scripts/silver_ronda.py correr --cap-semanal 75
    python scripts/silver_ronda.py estado
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import silver_estado as S  # noqa: E402
from scripts.filter_runner import weekly_usage  # noqa: E402

ROOT = S.ROOT
SILVER = S.SILVER
PYTHON = str(ROOT / ".venv" / "bin" / "python")
META = SILVER / "r4_meta.json"
CONFIRMAR = ("populismo", "doctrinarismo", "soberanismo", "personalismo")
SHARDS = {"haiku": 2, "sonnet": 2, "opus": 1}
# Opus no arranca una tanda por dos artículos: el arranque cuesta un contexto
# entero. Espera a juntar un lote razonable, salvo al final de la ronda.
OPUS_MIN = 40


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def corpus(juez: str, k: int) -> Path:
    return SILVER / f"corpus_{juez}_r4{'ab'[k]}.jsonl"


def votos_de(juez: str) -> dict[str, str]:
    return S._union(f"votos_{juez}_r4*.jsonl")


def _lineas(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [json.loads(x)["id"] for x in path.open(encoding="utf-8") if x.strip()]


def _escribe(path: Path, ids: list[str], raw: dict[str, dict], modo: str = "w") -> None:
    with path.open(modo, encoding="utf-8") as f:
        for i in ids:
            a = raw[i]
            f.write(json.dumps({"id": i, "title": a.get("title", ""), "text": a.get("text", "")},
                               ensure_ascii=False) + "\n")


def _raw(ids: set[str]) -> dict[str, dict]:
    return {a["id"]: a for a in S.iter_raw() if a["id"] in ids}


# ------------------------------------------------------------- preparar --

def cmd_preparar(args: argparse.Namespace) -> None:
    if META.exists() and not args.force:
        raise SystemExit(f"✗ {META.relative_to(ROOT)} ya existe. --force para rehacer.")
    gold = set(json.loads((ROOT / "annotation" / "gold_set_v2_ids.json").read_text()))
    E = S.todas()

    decidir = sorted(i for i, e in E.items() if e.estado == S.PENDIENTE and e.via == "p3")
    confirmar = sorted(i for i, e in E.items()
                       if e.via == "p1" and e.estado == S.UNICO and e.clase in CONFIRMAR)

    plan = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))["plan"]
    # Alternancia entre clases por rango: cada clase avanza a la par.
    colas = [list(v) for v in plan.values()]
    candidatos, objetivo = [], {}
    while any(colas):
        for cola in colas:
            if cola:
                c = cola.pop(0)
                candidatos.append(c["id"])
        colas = [c for c in colas if c]
    for clase, lista in plan.items():
        for c in lista:
            objetivo[c["id"]] = clase

    fuga = (set(decidir) | set(confirmar) | set(candidatos)) & gold
    if fuga:
        raise SystemExit(f"✗ {len(fuga)} artículos del gold en la ronda. Nada se escribe.")

    raw = _raw(set(decidir) | set(confirmar) | set(candidatos))
    _escribe(SILVER / "corpus_sust_decide.jsonl", decidir, raw)
    for k in range(SHARDS["haiku"]):
        _escribe(corpus("haiku", k), candidatos[k::SHARDS["haiku"]], raw)
    sonnet = confirmar + candidatos
    for k in range(SHARDS["sonnet"]):
        _escribe(corpus("sonnet", k), sonnet[k::SHARDS["sonnet"]], raw)
    for k in range(SHARDS["opus"]):
        corpus("opus", k).write_text("", encoding="utf-8")

    from src.agents.silver.codebook import build_system_prompt
    sha = hashlib.sha1(build_system_prompt(include_examples=True).encode()).hexdigest()[:12]
    META.write_text(json.dumps({
        "creado": datetime.now().isoformat(timespec="seconds"),
        "codebook_sha": sha, "plan": args.plan, "shards": SHARDS,
        "decidir_p3": decidir, "confirmar": confirmar,
        "candidatos": candidatos, "clase_objetivo": objetivo,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"  codebook {sha}")
    print(f"  decidir p3   {len(decidir):6,}  (opus)")
    print(f"  confirmar    {len(confirmar):6,}  (sonnet → opus si discrepa)  "
          + str(dict(collections.Counter(E[i].clase for i in confirmar))))
    print(f"  candidatos   {len(candidatos):6,}  (haiku + sonnet → opus si discrepan)")
    print(f"  ✓ {META.relative_to(ROOT)}")


def _intercala(plan: dict[str, list[dict]], ya: set[str]) -> list[str]:
    """Alternancia entre clases por rango: cada clase avanza a la par."""
    colas = [[c["id"] for c in v if c["id"] not in ya] for v in plan.values()]
    out: list[str] = []
    while any(colas):
        for cola in colas:
            if cola:
                out.append(cola.pop(0))
        colas = [c for c in colas if c]
    return out


def cmd_ampliar(args: argparse.Namespace) -> None:
    """Añade una tanda de minería o de confirmaciones al FINAL de las colas.

    Las colas son de solo-añadir (el cursor de cada runner es un número de
    línea), así que lo nuevo se juzga después de lo que ya estaba. El
    orquestador lee el plan al arrancar: hay que relanzarlo después.
    """
    meta = json.loads(META.read_text(encoding="utf-8"))
    gold = set(json.loads((ROOT / "annotation" / "gold_set_v2_ids.json").read_text()))
    ya = set(meta["candidatos"]) | set(meta["confirmar"]) | set(meta["decidir_p3"])

    cands, objetivo = [], {}
    if args.plan:
        plan = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))["plan"]
        cands = _intercala(plan, ya)
        objetivo = {c["id"]: clase for clase, lista in plan.items() for c in lista
                    if c["id"] in set(cands)}
    conf = []
    if args.confirmar_clases:
        clases = set(args.confirmar_clases.split(","))
        E = S.todas()
        conf = sorted(i for i, e in E.items() if e.via == "p1" and e.estado == S.UNICO
                      and e.clase in clases and i not in ya)
    if (set(cands) | set(conf)) & gold:
        raise SystemExit("✗ Hay artículos del gold en la ampliación. Nada se escribe.")
    if not cands and not conf:
        raise SystemExit("✗ Nada que añadir.")

    raw = _raw(set(cands) | set(conf))
    for k in range(SHARDS["haiku"]):
        _escribe(corpus("haiku", k), cands[k::SHARDS["haiku"]], raw, modo="a")
    # Para sonnet primero lo que balancea y después lo que solo confirma.
    sonnet = cands + conf
    for k in range(SHARDS["sonnet"]):
        _escribe(corpus("sonnet", k), sonnet[k::SHARDS["sonnet"]], raw, modo="a")

    meta["candidatos"] += cands
    meta["clase_objetivo"].update(objetivo)
    meta["confirmar"] += conf
    meta.setdefault("ampliaciones", []).append({
        "fecha": datetime.now().isoformat(timespec="seconds"), "plan": args.plan,
        "candidatos": len(cands), "confirmar": len(conf),
        "confirmar_clases": args.confirmar_clases})
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  + {len(cands):,} candidatos · + {len(conf):,} confirmaciones")
    if conf:
        E = E if args.confirmar_clases else S.todas()
        print("    confirmaciones por clase: " +
              str(dict(collections.Counter(E[i].clase for i in conf))))
    print("  ⚠ relanza el orquestador para que lea el plan nuevo.")


def cmd_priorizar(args: argparse.Namespace) -> None:
    """Pone primero en las colas de haiku y sonnet los artículos de un plan.

    Las colas son de solo-añadir, así que lo último que se amplía es lo último
    que se juzga. Reordenar es seguro con los runners PARADOS: el cursor vuelve
    a 0 y `silver_agent next` salta por id todo lo ya votado, así que nada se
    pierde ni se repite.
    """
    vivos = [p.stem for p in SILVER.glob("runner_*_r4*.pid")
             if vivo(p.stem.removeprefix("runner_"))]
    try:
        os.kill(int((SILVER / "ronda_r4.pid").read_text().strip()), 0)
        vivos.append("orquestador")
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        pass
    if vivos:
        raise SystemExit(f"✗ Hay procesos vivos ({vivos}): páralos antes de reordenar.")
    plan = json.loads((ROOT / args.plan).read_text(encoding="utf-8"))["plan"]
    primero = {c["id"] for v in plan.values() for c in v}
    for juez in ("haiku", "sonnet"):
        for k in range(SHARDS[juez]):
            path = corpus(juez, k)
            lineas = [x for x in path.open(encoding="utf-8") if x.strip()]
            delante = [x for x in lineas if json.loads(x)["id"] in primero]
            detras = [x for x in lineas if json.loads(x)["id"] not in primero]
            tmp = path.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(delante + detras), encoding="utf-8")
            tmp.replace(path)
            estado = SILVER / f"agent_batches_{juez}_r4{'ab'[k]}" / "state.json"
            if estado.exists():
                d = json.loads(estado.read_text(encoding="utf-8"))
                d.update(cursor=0, pending_batch=None, session_tokens=0)
                estado.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  {path.name}: {len(delante):,} del plan primero, {len(detras):,} detrás")


# -------------------------------------------------------------- correr --

def necesita_opus(meta: dict) -> list[str]:
    """Artículos de r4 donde haiku y sonnet ya votaron y no hay mayoría."""
    h, s, o = votos_de("haiku"), votos_de("sonnet"), votos_de("opus")
    p1 = S._votos(SILVER / "votos_haiku.jsonl")
    out = []
    for i in meta["confirmar"] + meta["candidatos"]:
        if i in o:
            continue
        v = {"haiku": h.get(i) or (p1.get(i) if i in meta["confirmar"] else None),
             "sonnet": s.get(i)}
        if v["haiku"] is None or v["sonnet"] is None:
            continue
        clase, estado = S.mayoria_perezosa({k: c for k, c in v.items() if c})
        if estado == S.PENDIENTE:
            out.append(i)
    return out


def vivo(tag: str) -> bool:
    pidf = SILVER / f"runner_{tag}.pid"
    if not pidf.exists():
        return False
    try:
        os.kill(int(pidf.read_text().strip()), 0)
    except (ValueError, ProcessLookupError, PermissionError):
        return False
    return True


def pendientes(juez: str, sufijo: str, path: Path) -> int:
    hechos = set(S._votos(SILVER / f"votos_{juez}{sufijo}.jsonl"))
    return sum(1 for i in _lineas(path) if i not in hechos)


def lanza(juez: str, sufijo: str, path: Path, cap: float, budget: int) -> None:
    tag = f"{juez}{sufijo}"
    logf = SILVER / f"runner_{tag}.log"
    with logf.open("a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] ── lanzado por silver_ronda ──\n")
        subprocess.Popen(
            [PYTHON, "-u", str(ROOT / "scripts" / "silver_runner.py"),
             "--juez", juez, "--sufijo", sufijo, "--corpus", str(path.relative_to(ROOT)),
             "--cap-semanal", str(cap), "--budget", str(budget)],
            stdout=f, stderr=subprocess.STDOUT, cwd=ROOT, start_new_session=True)


def cmd_correr(args: argparse.Namespace) -> None:
    # Opus es el juez lento y le llega todo lo empatado: el número de agentes
    # que lo atienden se puede subir sin rehacer nada (reparto por hash).
    SHARDS["opus"] = args.opus_shards
    meta = json.loads(META.read_text(encoding="utf-8"))
    claude_bin = shutil.which("claude") or "claude"
    (SILVER / "ronda_r4.pid").write_text(str(os.getpid()), encoding="utf-8")
    # Que el Mac no se duerma mientras viva este proceso (-w lo ata a su PID).
    subprocess.Popen(["caffeinate", "-ims", "-w", str(os.getpid())], start_new_session=True)

    raw_cache: dict[str, dict] = {}
    log(f"ronda r4 · tope semanal {args.cap_semanal:.0f} % · budget {args.budget:,}")
    while True:
        uso = weekly_usage(claude_bin)
        if uso and uso[0] >= args.cap_semanal:
            log(f"⏹ semanal al {uso[0]:.0f} %: no lanzo a nadie más. Fin.")
            return

        # Lo nuevo para opus: se reparte por hash para que no dependa del orden
        # de llegada, y se AÑADE (el cursor del runner es un número de línea).
        ya = set()
        for k in range(SHARDS["opus"]):
            ya.update(_lineas(corpus("opus", k)))
        nuevos = [i for i in necesita_opus(meta) if i not in ya]
        if nuevos:
            falta = {i for i in nuevos if i not in raw_cache}
            if falta:
                raw_cache.update(_raw(falta))
            for k in range(SHARDS["opus"]):
                mios = [i for i in nuevos if int(i[:8], 16) % SHARDS["opus"] == k]
                if mios:
                    _escribe(corpus("opus", k), mios, raw_cache, modo="a")
            log(f"   +{len(nuevos)} para opus (haiku y sonnet discrepan)")

        trabajos = [("opus", "_sust_dec", SILVER / "corpus_sust_decide.jsonl")]
        trabajos += [(j, f"_r4{'ab'[k]}", corpus(j, k))
                     for j in ("haiku", "sonnet") for k in range(SHARDS[j])]
        trabajos += [("opus", f"_r4{'ab'[k]}", corpus("opus", k)) for k in range(SHARDS["opus"])]

        linea, activos, restantes = [], 0, 0
        upstream = 0
        for juez, suf, path in trabajos:
            n = pendientes(juez, suf, path)
            restantes += n
            if juez in ("haiku", "sonnet"):
                upstream += n
            tag = f"{juez}{suf}"
            if vivo(tag):
                activos += 1
            elif n and (juez != "opus" or suf == "_sust_dec" or n >= OPUS_MIN or upstream == 0):
                log(f"▶ lanzo {tag} ({n:,} pendientes)")
                lanza(juez, suf, path, args.cap_semanal, args.budget)
                activos += 1
                time.sleep(3)
            linea.append(f"{tag}={n:,}")
        pct = f" · semanal {uso[0]:.0f} %" if uso else ""
        log(f"   pendientes: {' '.join(linea)}{pct}")

        if restantes == 0 and activos == 0:
            log("✓ ronda r4 completa.")
            return
        time.sleep(args.intervalo)


# -------------------------------------------------------------- estado --

def cmd_estado(args: argparse.Namespace) -> None:
    meta = json.loads(META.read_text(encoding="utf-8"))
    E = S.todas()
    for nombre in ("decidir_p3", "confirmar", "candidatos"):
        ids = meta[nombre]
        est = collections.Counter(E[i].estado if i in E else "sin_votos" for i in ids)
        print(f"  {nombre:<12}{len(ids):6,}  " + "  ".join(f"{k}={v:,}" for k, v in est.most_common()))
    obj = meta["clase_objetivo"]
    hechos = [i for i in meta["candidatos"] if i in E and E[i].estado != S.PENDIENTE]
    if hechos:
        print(f"\n  Candidatos resueltos: {len(hechos):,}   (fila = clase buscada, col = resultado)")
        tabla = collections.defaultdict(collections.Counter)
        for i in hechos:
            tabla[obj[i]][E[i].clase or E[i].estado] += 1
        for c, fila in tabla.items():
            n = sum(fila.values())
            print(f"    {c:<16} n={n:5,}  acierto {fila[c] / n:5.1%}  " +
                  " ".join(f"{k[:5]}={v}" for k, v in fila.most_common(5)))
    conf = [i for i in meta["confirmar"] if i in E and E[i].via == "r4"]
    if conf:
        p1 = S._votos(SILVER / "votos_haiku.jsonl")
        ok = sum(1 for i in conf if E[i].clase == p1.get(i))
        print(f"\n  Confirmaciones resueltas: {len(conf):,} · se mantiene la de p1: {ok / len(conf):.1%}")
    print()
    print(json.dumps(S.resumen(E)["por_clase"], ensure_ascii=False))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar")
    p.add_argument("--plan", default="data/silver/plan_r4.json")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_preparar)
    p = sub.add_parser("ampliar")
    p.add_argument("--plan", default=None, help="otra salida de silver_mine.py")
    p.add_argument("--confirmar-clases", default=None,
                   help="clase,clase: etiquetas de un solo juez (p1) a confirmar")
    p.set_defaults(func=cmd_ampliar)
    p = sub.add_parser("priorizar")
    p.add_argument("--plan", required=True, help="plan cuyos artículos van primero")
    p.set_defaults(func=cmd_priorizar)
    p = sub.add_parser("correr")
    p.add_argument("--cap-semanal", type=float, default=75.0)
    p.add_argument("--budget", type=int, default=110_000)
    p.add_argument("--intervalo", type=float, default=180.0)
    p.add_argument("--opus-shards", type=int, default=2)
    p.set_defaults(func=cmd_correr)
    p = sub.add_parser("estado")
    p.set_defaults(func=cmd_estado)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
