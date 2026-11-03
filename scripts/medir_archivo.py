#!/usr/bin/env python3
"""Mide cuánto archivo histórico NUEVO tiene cada fuente, sin descargar artículos.

Para balancear el silver ya no basta con minar el corpus: populismo y
doctrinarismo se agotaron ahí (la 2ª minería acertó 8,9 % y 6,1 %). Donde sí
aparecen es en un puñado de medios partidistas e independientes, y varios se
rastrearon apenas por su RSS (lo reciente): colombiainforma tiene 129 artículos
en el corpus, desdeabajo 168 de ~24.000 publicados.

Este script solo lee los sitemaps XML de cada fuente —ningún artículo— y
cruza las URLs con la base del scraper para contar las que nunca se bajaron.
Con la tasa de populismo/doctrinarismo medida en el silver y la tasa de paso
del filtro de cada fuente, estima cuántos ejemplos daría rastrear su archivo.

    python scripts/medir_archivo.py --fuentes desdeabajo,colombiainforma
    python scripts/medir_archivo.py --grupo balance
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trafilatura.sitemaps import sitemap_search  # noqa: E402

import silver_estado as S  # noqa: E402
from src.scraper.db import is_already_scraped  # noqa: E402
from src.scraper.parser import _filter_political_urls  # noqa: E402
from src.scraper.sources import SOURCES  # noqa: E402
from src.scraper.urls import dedupe_normalized  # noqa: E402

ROOT = S.ROOT
OUT = ROOT / "data" / "silver" / "medicion_archivo.json"  # --grupo resto escribe medicion_archivo_resto.json

# Los medios donde el silver ya midió populismo/doctrinarismo, de los dos
# lados. El lado derecho va completo a propósito: si solo crece la izquierda,
# el modelo aprende "izquierda = populismo/doctrinarismo" y no el encuadre.
GRUPOS = {
    "izquierda": [
        "unionpatriotica", "congresodelospueblos", "periferiaprensa", "colombiainforma",
        "semanariovoz", "revistasur", "desdeabajo", "partidocomunes", "elturbion",
        "pacocol", "laotracara", "archipielagopress", "pactohistorico", "mais",
        "colombiaplural", "nasaacin", "cna_colombia", "cric", "indepaz", "alianzaverde",
    ],
    "derecha": [
        "losirreverentes", "elexpediente", "confidencialnoticias", "cabal",
        "contextoganadero", "fedegan", "sac", "valorescristianos", "elcatolicismo",
        "partidoconservador", "cambioradical", "partidodelau", "soyliga", "partidomira",
    ],
    "centro": ["dignidadycompromiso", "nuevoliberalismo", "las2orillas", "cambio", "pares"],
}
GRUPOS["balance"] = GRUPOS["izquierda"] + GRUPOS["derecha"] + GRUPOS["centro"]
# El resto de la red: todo lo que no es nacional ni judicial (allí la tasa de
# populismo/doctrinarismo es ~0) y no se rastreó ya. Sirve para DIVERSIFICAR:
# muchos medios aportando poco cada uno, en vez de pocos aportando mucho.
_RASTREADOS = set(GRUPOS["balance"]) | {"icpcolombia", "acore"}
GRUPOS["resto"] = sorted(n for n, c in SOURCES.items()
                         if c.get("category") not in ("nacional", "judicial") and n not in _RASTREADOS)
_ANIO = re.compile(r"/(20[0-2]\d)/")


def _sitemap(url: str, timeout: int) -> tuple[list[str], str | None]:
    out: list[str] = []
    err: list[str] = []

    def run() -> None:
        try:
            out.extend(sitemap_search(url) or [])
        except Exception as exc:  # noqa: BLE001 — se reporta, no se aborta
            err.append(f"{type(exc).__name__}: {str(exc)[:80]}")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return list(out), f"timeout {timeout}s (parcial)"
    return out, (err[0] if err else None)


def tasas_silver() -> dict[str, dict[str, float]]:
    """Por fuente: juzgados, populismo, doctrinarismo y tasa de paso del filtro."""
    E = S.todas()
    fuente, crudo = {}, collections.Counter()
    with (ROOT / "data" / "raw" / "articles.jsonl").open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                a = json.loads(linea)
                fuente[a["id"]] = a.get("source")
    sin_filtrar = ROOT / "data" / "raw" / "articles_unfiltered.jsonl"
    if sin_filtrar.exists():
        with sin_filtrar.open(encoding="utf-8") as f:
            for linea in f:
                if linea.strip():
                    crudo[json.loads(linea).get("source")] += 1
    filtrado = collections.Counter(fuente.values())
    out: dict[str, dict[str, float]] = collections.defaultdict(lambda: collections.Counter())
    for i, e in E.items():
        s = fuente.get(i)
        if not s or e.estado == S.PENDIENTE:
            continue
        out[s]["juzgados"] += 1
        if e.entrena and e.clase in ("populismo", "doctrinarismo", "soberanismo"):
            out[s][e.clase] += 1
    for s in set(filtrado) | set(crudo):
        out[s]["paso_filtro"] = filtrado[s] / crudo[s] if crudo[s] else 0.5
        out[s]["en_corpus"] = filtrado[s]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fuentes", default=None, help="nombres separados por coma")
    ap.add_argument("--grupo", default="balance", choices=list(GRUPOS))
    ap.add_argument("--timeout", type=int, default=420, help="segundos por sitemap")
    ap.add_argument("--paralelo", type=int, default=6)
    args = ap.parse_args()

    nombres = args.fuentes.split(",") if args.fuentes else GRUPOS[args.grupo]
    faltan = [n for n in nombres if n not in SOURCES]
    if faltan:
        raise SystemExit(f"✗ no están en sources.py: {faltan}")
    lado = {n: g for g in ("izquierda", "derecha", "centro") for n in GRUPOS[g]}

    print(f"  midiendo {len(nombres)} sitemaps (hasta {args.timeout}s cada uno)…", flush=True)
    crudo: dict[str, tuple[list[str], str | None]] = {}
    pendientes = list(nombres)
    while pendientes:
        tanda, pendientes = pendientes[: args.paralelo], pendientes[args.paralelo:]
        hilos = {}
        for n in tanda:
            res: dict = {}
            t = threading.Thread(target=lambda n=n, res=res: res.update(
                r=_sitemap(SOURCES[n]["url"], args.timeout)), daemon=True)
            t.start()
            hilos[n] = (t, res)
        for n, (t, res) in hilos.items():
            t.join(args.timeout + 30)
            crudo[n] = res.get("r", ([], "sin respuesta"))
            print(f"    {n:<22} {len(crudo[n][0]):>7,} URLs  {crudo[n][1] or ''}", flush=True)

    tasas = tasas_silver()
    filas = []
    for n in nombres:
        conf = SOURCES[n]
        urls, err = crudo[n]
        urls = dedupe_normalized(urls)
        politicas = _filter_political_urls(urls, conf.get("url_filters", [])) \
            if conf.get("mode") == "sitemap" else urls
        nuevas = [u for u in politicas if not is_already_scraped(u)]
        anios = collections.Counter(m.group(1) for u in nuevas if (m := _ANIO.search(u)))
        t = tasas.get(n, collections.Counter())
        jz = t.get("juzgados", 0)
        tasa_pop = t.get("populismo", 0) / jz if jz else 0.0
        tasa_doc = t.get("doctrinarismo", 0) / jz if jz else 0.0
        tasa_sob = t.get("soberanismo", 0) / jz if jz else 0.0
        paso = t.get("paso_filtro", 0.5)
        filas.append({
            "fuente": n, "lado": lado.get(n, "?"), "categoria": conf.get("category"),
            "sitemap": len(urls), "politicas": len(politicas), "nuevas": len(nuevas),
            "en_corpus": int(t.get("en_corpus", 0)), "juzgados": jz,
            "tasa_pop": round(tasa_pop, 3), "tasa_doc": round(tasa_doc, 3),
            "paso_filtro": round(paso, 2),
            "esperado_pop": round(len(nuevas) * paso * tasa_pop),
            "esperado_doc": round(len(nuevas) * paso * tasa_doc),
            "tasa_sob": round(tasa_sob, 3),
            "esperado_sob": round(len(nuevas) * paso * tasa_sob),
            "anios": dict(sorted(anios.items())), "error": err,
        })

    out = OUT if args.grupo == "balance" else OUT.with_name(f"medicion_archivo_{args.grupo}.json")
    out.write_text(json.dumps({"medido": time.strftime("%Y-%m-%d %H:%M"), "fuentes": filas},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  {'fuente':<22}{'lado':<10}{'nuevas':>8}{'corpus':>7}{'filtro':>7}"
          f"{'%pop':>6}{'%doc':>6}{'≈pop':>6}{'≈doc':>6}  años")
    for r in sorted(filas, key=lambda r: -(r["esperado_pop"] + r["esperado_doc"])):
        anios = ",".join(f"{a[2:]}:{c}" for a, c in r["anios"].items()) or "—"
        print(f"  {r['fuente']:<22}{r['lado']:<10}{r['nuevas']:>8,}{r['en_corpus']:>7,}"
              f"{r['paso_filtro']:>7.0%}{r['tasa_pop']:>6.0%}{r['tasa_doc']:>6.0%}"
              f"{r['esperado_pop']:>6}{r['esperado_doc']:>6}  {anios[:60]}"
              + (f"  ⚠ {r['error']}" if r["error"] else ""))
    for g in ("izquierda", "derecha", "centro"):
        sub = [r for r in filas if r["lado"] == g]
        print(f"  Σ {g:<10} nuevas {sum(r['nuevas'] for r in sub):>7,}  "
              f"≈pop {sum(r['esperado_pop'] for r in sub):>5}  ≈doc {sum(r['esperado_doc'] for r in sub):>5}")
    print(f"\n  ✓ {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
