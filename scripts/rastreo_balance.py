#!/usr/bin/env python3
"""Rastreo dirigido para balancear el silver: populismo y doctrinarismo.

El corpus ya no da más de esas dos clases (la 2ª minería acertó 8,9 % y
6,1 %). Donde aparecen es en un puñado de medios partidistas e independientes,
y varios se habían rastreado solo por su RSS: lo reciente, no el archivo.
`medir_archivo.py` midió cuánto archivo nuevo tiene cada uno.

Tres pasos, cada uno reanudable:

    descubrir  sitemaps (y feeds paginados de WordPress) → URLs nuevas por fuente
    rastrear   scrape + limpieza + calidad del scraper (process_url), SIN filtro
               LLM, con tope por fuente → data/raw/rastreo_balance_bruto.jsonl
    cribar     la criba TF-IDF del silver ordena lo bajado y deja SOLO los
               candidatos de las clases que faltan → data/silver/plan_balance.json

Lo que no pasa la criba no entra a ningún corpus: el bruto es un archivo de
trabajo, no corpus. Y nada de esto toca data/raw/articles.jsonl.

El riesgo que se vigila: casi todo el archivo es de izquierda. Si solo crece
ese lado, el modelo aprende "izquierda = populismo/doctrinarismo" en vez del
encuadre. Por eso el lado derecho se rastrea completo y el izquierdo con tope,
y la criba reparte los cupos por lado.

    python scripts/rastreo_balance.py descubrir
    python scripts/rastreo_balance.py rastrear --workers 10
    python scripts/rastreo_balance.py cribar
"""

from __future__ import annotations

import argparse
import collections
import html
import json
import random
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.scraper.db import is_already_scraped, mark_as_scraped  # noqa: E402
from src.scraper.parser import _filter_political_urls  # noqa: E402
from src.scraper.sources import SOURCES  # noqa: E402
from src.scraper.urls import dedupe_normalized  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "data" / "silver" / "rastreo"
BRUTO = ROOT / "data" / "raw" / "rastreo_balance_bruto.jsonl"
LOG = DIR / "rastreo.log"

# Tope de artículos CONSERVADOS por fuente. La izquierda tiene ~120.000 URLs
# nuevas y la derecha ~45.000: sin tope, el silver nuevo saldría casi entero
# de cinco medios de izquierda.
IZQUIERDA = {
    "semanariovoz": 1500, "pacocol": 1500, "colombiainforma": 1500,
    "archipielagopress": 1200, "revistasur": 1500, "elturbion": 1200,
    "congresodelospueblos": 1500, "periferiaprensa": 1500, "unionpatriotica": 600,
    "partidocomunes": 1000, "laotracara": 1000, "desdeabajo": 1500,
}
DERECHA = {
    "contextoganadero": 5000, "cabal": 1000, "losirreverentes": 3000,
    "elexpediente": 5000, "confidencialnoticias": 4000, "acore": 2000,
    "icpcolombia": 2000, "partidoconservador": 500, "cambioradical": 2000,
    "partidomira": 1000, "elcatolicismo": 1000,
    "centrodemocratico": 3000,   # añadido 28-oct (lote `partidos`): el partido de gobierno 2018-22 faltaba
}
TOPES = {**IZQUIERDA, **DERECHA}
LADO = {**{k: "izquierda" for k in IZQUIERDA}, **{k: "derecha" for k in DERECHA}}

# Lotes de rastreo, cada uno con sus ficheros. `balance` fue el primero (los
# 25 medios partidistas). `diverso` sale de `medir_archivo.py --grupo resto`:
# muchos medios aportando poco cada uno, para que ninguna clase escasa dependa
# de un puñado de medios. Sin reparto por lado: ahí el control es el tope
# por medio dentro de cada clase.
LOTES = {
    "balance": {"bruto": "rastreo_balance_bruto.jsonl", "candidatos": "articles_balance.jsonl",
                "plan": "plan_balance.json", "filtro": "filtro.jsonl"},
    "diverso": {"bruto": "rastreo_diverso_bruto.jsonl", "candidatos": "articles_diverso.jsonl",
                "plan": "plan_diverso.json", "filtro": "filtro_diverso.jsonl"},
    # 2ª pasada por los mismos medios partidistas: más hondo en su archivo y
    # lo reciente primero. El tope por medio del silver (15 % en las escasas)
    # crece con la clase, así que caben más de cada uno sin concentrar.
    "balance2": {"bruto": "rastreo_balance2_bruto.jsonl", "candidatos": "articles_balance2.jsonl",
                 "plan": "plan_balance2.json", "filtro": "filtro_balance2.jsonl"},
    # Partidos que no estaban en sources.py. De los candidatos revisados el
    # 28-oct solo el Centro Democrático tenía archivo: los dominios de
    # Salvación Nacional, Fuerza Ciudadana, Creemos y Colombia Justa Libres
    # están caídos, aparcados o secuestrados (spam de apuestas).
    "partidos": {"bruto": "rastreo_partidos_bruto.jsonl", "candidatos": "articles_partidos.jsonl",
                 "plan": "plan_partidos.json", "filtro": "filtro_partidos.jsonl"},
    # 2ª pasada (29-oct) por donde el 1er lote rindió: los 37 medios diversos
    # con ≥2 % de candidatos escasos por artículo bajado, y los partidistas con
    # ≥8 % (los dos lados). Lo que queda de su archivo es más viejo: sube los
    # conteos, no la proporción de 2026.
    "diverso2": {"bruto": "rastreo_diverso2_bruto.jsonl", "candidatos": "articles_diverso2.jsonl",
                 "plan": "plan_diverso2.json", "filtro": "filtro_diverso2.jsonl"},
    "balance3": {"bruto": "rastreo_balance3_bruto.jsonl", "candidatos": "articles_balance3.jsonl",
                 "plan": "plan_balance3.json", "filtro": "filtro_balance3.jsonl"},
}
MEDICION_RESTO = ROOT / "data" / "silver" / "medicion_archivo_resto.json"

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
_LINK = re.compile(r"<item>.*?<link>\s*([^<\s]+)\s*</link>", re.S)
# Sub-sitemaps y URLs que no son artículos: no se siguen ni se bajan.
_NO_SITEMAP = re.compile(r"(tag|category|categoria|author|autor|page|attachment|"
                         r"product|portfolio|media|image|video)[-_]?sitemap", re.I)
_NO_ARTICULO = re.compile(
    r"/(tag|tags|etiqueta|etiquetas|category|categoria|author|autor|page|wp-content|"
    r"feed|attachment|search|buscar)/|\.(jpg|jpeg|png|gif|webp|pdf|mp3|mp4|xml)$", re.I)

_LOG_LOCK = threading.Lock()


def log(msg: str) -> None:
    linea = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(linea, flush=True)
    DIR.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK, LOG.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def _get(url: str, timeout: int = 30) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": _UA, "Accept": "text/html,application/xml;q=0.9,*/*;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:  # noqa: BLE001 — una fuente rota no tumba el rastreo
        return None


def _expande(xml: str, profundidad: int = 0) -> list[str]:
    locs = _LOC.findall(xml)
    if "<sitemapindex" not in xml:
        return locs
    out: list[str] = []
    for sub in locs:
        if _NO_SITEMAP.search(sub) or profundidad >= 3:
            continue
        hijo = _get(sub, timeout=60)
        time.sleep(0.5)
        if hijo:
            out.extend(_expande(hijo, profundidad + 1))
    return out


def _feed_paginado(base: str, max_paginas: int = 400) -> list[str]:
    out: list[str] = []
    for n in range(1, max_paginas + 1):
        xml = _get(f"{base.rstrip('/')}/feed/?paged={n}")
        enlaces = _LINK.findall(xml or "")
        if not enlaces:
            break
        out.extend(enlaces)
        time.sleep(0.7)
    return out


def descubre(nombre: str) -> list[str]:
    base = SOURCES[nombre]["url"].rstrip("/")
    urls: list[str] = []
    for ruta in ("/sitemap_index.xml", "/wp-sitemap.xml", "/sitemap.xml", "/post-sitemap.xml"):
        xml = _get(base + ruta)
        if xml and "<loc>" in xml:
            urls = _expande(xml)
            if urls:
                break
    if len(urls) < 50:
        urls += _feed_paginado(base)
    if len(urls) < 50:
        from trafilatura.sitemaps import sitemap_search
        res: list[str] = []
        t = threading.Thread(target=lambda: res.extend(sitemap_search(base) or []), daemon=True)
        t.start()
        t.join(900)
        urls += res
    return urls


_ANIO_URL = re.compile(r"/(20[0-2]\d)/")


def _prioridad_anio(url: str) -> int:
    """Lo reciente primero; sin año en la URL, en medio."""
    m = _ANIO_URL.search(url)
    if not m:
        return 1
    return 0 if m.group(1) >= "2024" else (2 if m.group(1) >= "2020" else 3)


def cmd_descubrir(args: argparse.Namespace) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    fuentes = args.fuentes.split(",") if args.fuentes else list(TOPES)

    def una(n: str) -> None:
        dest = DIR / f"urls_{n}.txt"
        if dest.exists() and not args.force:
            return
        crudas = dedupe_normalized(descubre(n))
        conf = SOURCES[n]
        if conf.get("mode") == "sitemap":
            crudas = _filter_political_urls(crudas, conf.get("url_filters", []))
        utiles = [u for u in crudas if not _NO_ARTICULO.search(u)]
        nuevas = [u for u in utiles if not is_already_scraped(u)]
        random.Random(42).shuffle(nuevas)
        if args.recientes:
            # El gold (test) es 44 % de 2026 y el archivo se va a 2021-2023: si
            # las clases escasas salen del archivo viejo, el año se vuelve atajo.
            nuevas.sort(key=_prioridad_anio)
        dest.write_text("\n".join(nuevas), encoding="utf-8")
        log(f"descubrir {n:<22} crudas {len(crudas):>7,} · artículos {len(utiles):>7,} · nuevas {len(nuevas):>7,}")

    hilos = [threading.Thread(target=una, args=(n,), daemon=True) for n in fuentes]
    for i in range(0, len(hilos), args.paralelo):
        tanda = hilos[i:i + args.paralelo]
        for t in tanda:
            t.start()
        for t in tanda:
            t.join()


_WRITE = threading.Lock()


def cmd_rastrear(args: argparse.Namespace) -> None:
    from src.scraper.pipeline import process_url

    existentes: set[str] = set()
    conservados: collections.Counter = collections.Counter()
    if BRUTO.exists():
        for linea in BRUTO.open(encoding="utf-8"):
            if linea.strip():
                a = json.loads(linea)
                existentes.add(a["id"])
                conservados[a.get("source")] += 1
    fuentes = args.fuentes.split(",") if args.fuentes else list(TOPES)

    def una(n: str) -> None:
        archivo = DIR / f"urls_{n}.txt"
        if not archivo.exists():
            log(f"rastrear {n}: sin URLs descubiertas")
            return
        urls = [u for u in archivo.read_text(encoding="utf-8").splitlines() if u.strip()]
        conf = SOURCES[n]
        tope, hechos, fallos_seguidos = TOPES.get(n, 1000), 0, 0
        motivos: collections.Counter = collections.Counter()
        for url in urls:
            if conservados[n] >= tope:
                break
            if is_already_scraped(url):
                continue
            art, motivo = process_url(url, n, conf["category"], None, "", args.min_chars, False)
            hechos += 1
            motivos[motivo] += 1
            if art is not None:
                h = art.pop("content_hash")
                with _WRITE:
                    nuevo = art["id"] not in existentes
                    if nuevo:
                        existentes.add(art["id"])
                        with BRUTO.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(art, ensure_ascii=False) + "\n")
                mark_as_scraped(art["url"], h, n, conf["category"], art["scraped_at"])
                if nuevo:
                    conservados[n] += 1
                fallos_seguidos = 0
            elif motivo == "scrape_fail":
                fallos_seguidos += 1
                if fallos_seguidos in (15, 30):
                    time.sleep(120)          # el medio puede estar limitándonos
                if fallos_seguidos >= 45:
                    log(f"rastrear {n}: {fallos_seguidos} fallos seguidos, lo dejo")
                    break
            else:
                fallos_seguidos = 0
            if hechos % 200 == 0:
                log(f"rastrear {n:<22} {hechos:>6,} vistas · {conservados[n]:>5,}/{tope} conservados · "
                    + " ".join(f"{k}={v}" for k, v in motivos.most_common(4)))
            time.sleep(args.pausa)
        log(f"✓ rastrear {n:<22} {hechos:,} vistas · {conservados[n]:,} conservados · "
            + " ".join(f"{k}={v}" for k, v in motivos.most_common(6)))

    hilos = [threading.Thread(target=una, args=(n,), daemon=True) for n in fuentes]
    activos: list[threading.Thread] = []
    for t in hilos:
        while len([a for a in activos if a.is_alive()]) >= args.workers:
            time.sleep(5)
        t.start()
        activos.append(t)
    for t in activos:
        t.join()
    log(f"rastreo terminado · {sum(conservados.values()):,} artículos en {BRUTO.relative_to(ROOT)}")


CANDIDATOS = ROOT / "data" / "raw" / "articles_balance.jsonl"
PLAN = ROOT / "data" / "silver" / "plan_balance.json"
FILTRO = DIR / "filtro.jsonl"
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def cmd_retitular(args: argparse.Namespace) -> None:
    """Rehace el titular de los artículos que comparten título con todo su medio.

    trafilatura toma a veces un encabezado del sitio por titular: los 2.454
    artículos del Centro Democrático salieron titulados «alvarouribe.com».
    La criba los descartaba como duplicados por título, y el input del modelo
    habría llevado una huella del medio en cada texto. El <title> de la página
    sí trae el titular (con el sufijo del medio, que `build_model_input` ya
    quita). Si también ahí se repite, el titular queda vacío.
    """
    from concurrent.futures import ThreadPoolExecutor

    filas = [json.loads(x) for x in BRUTO.open(encoding="utf-8") if x.strip()]
    rep = collections.Counter((a.get("source"), a.get("title") or "") for a in filas)
    malos = [a for a in filas if rep[(a.get("source"), a.get("title") or "")] >= args.min_repetidos]
    log(f"retitular: {len(malos):,} de {len(filas):,} con un título que se repite "
        f"≥{args.min_repetidos} veces en su medio")

    def uno(a: dict) -> tuple[str, str]:
        m = _TITLE_TAG.search(_get(a["url"]) or "")
        time.sleep(args.pausa)
        return a["id"], html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""

    with ThreadPoolExecutor(args.workers) as ex:
        nuevos = dict(ex.map(uno, malos))
    rep_nuevos = collections.Counter(nuevos.values())
    vacios = 0
    for a in filas:
        if a["id"] in nuevos:
            t = nuevos[a["id"]]
            if not t or rep_nuevos[t] >= args.min_repetidos:
                t, vacios = "", vacios + 1
            a["title"] = t
    tmp = BRUTO.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for a in filas:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    tmp.replace(BRUTO)
    log(f"✓ retitular: {len(nuevos) - vacios:,} titulares rehechos · {vacios:,} quedan vacíos")


def usa_lote(nombre: str, tope: int, min_nuevas: int) -> None:
    """Apunta los ficheros y los topes al lote elegido."""
    global BRUTO, CANDIDATOS, PLAN, FILTRO, TOPES, LADO
    f = LOTES[nombre]
    BRUTO = ROOT / "data" / "raw" / f["bruto"]
    CANDIDATOS = ROOT / "data" / "raw" / f["candidatos"]
    PLAN = ROOT / "data" / "silver" / f["plan"]
    FILTRO = DIR / f["filtro"]
    if nombre.startswith("diverso"):
        filas = json.loads(MEDICION_RESTO.read_text(encoding="utf-8"))["fuentes"]
        # Las estimaciones por medio salen de pocos artículos juzgados: sirven
        # para ORDENAR (los más prometedores primero), no para dar más cupo.
        filas = sorted((r for r in filas if r["nuevas"] >= min_nuevas and r["fuente"] in SOURCES),
                       key=lambda r: -(r["esperado_pop"] + r["esperado_doc"] + r["esperado_sob"]))
        TOPES = {r["fuente"]: tope for r in filas}
        LADO = {n: "diverso" for n in TOPES}
# Fracción esperada de candidatos que los jueces confirman en su clase,
# medida en el 1er lote del rastreo (28-oct, sobre ~2.350 juzgados):
# populismo 33 %, doctrinarismo 40 %, soberanismo 65 %.
ACIERTO = {"populismo": 0.33, "doctrinarismo": 0.40, "soberanismo": 0.65,
           "personalismo": 0.5, "globalismo": 0.6, "conservadurismo": 0.6}


def cmd_cribar(args: argparse.Namespace) -> None:
    """La criba del silver ordena lo bajado; solo quedan las clases que faltan.

    Cupos por clase = (objetivo − etiquetas actuales) / acierto esperado. Dentro
    de cada clase se alterna derecha/izquierda mientras la derecha tenga
    candidatos sobre el umbral, y ningún medio pasa del tope.
    """
    import numpy as np

    import silver_estado as S
    from silver_mine import _doc, _titulo_norm, entrena_criba

    E = S.todas()
    # Todo lo ya juzgado entrena la criba, también lo del lote anterior: son
    # justo los ejemplos de las clases escasas que la criba necesita.
    raw = {a["id"]: a for a in S.iter_raw()}
    # Los candidatos que ESTE lote ya eligió vuelven a competir: así repetir la
    # criba (p. ej. con otro --desde) re-elige en vez de saltarse lo ya elegido.
    propios = ({json.loads(x)["id"] for x in CANDIDATOS.open(encoding="utf-8") if x.strip()}
               if CANDIDATOS.exists() else set())
    bruto = {}
    viejos = 0
    for linea in BRUTO.open(encoding="utf-8"):
        if linea.strip():
            a = json.loads(linea)
            if args.desde and 0 < S.anio(a) < args.desde:     # sin fecha no es "viejo"
                viejos += 1
                continue
            if (a["id"] not in raw or a["id"] in propios) and a["id"] not in E:
                bruto[a["id"]] = a
    print(f"  bajados sin juzgar: {len(bruto):,}"
          + (f" · fuera por anteriores a {args.desde}: {viejos:,}" if args.desde else ""))

    vec, clf, ids_tr, y = entrena_criba(raw, E)
    clases = list(clf.classes_)
    ids = list(bruto)
    P = clf.predict_proba(vec.transform([_doc(bruto[i]) for i in ids]))

    gold = set(json.loads((ROOT / "annotation" / "gold_set_v2_ids.json").read_text()))
    vistos = {_titulo_norm(raw[i].get("title")) for i in gold | set(ids_tr) if i in raw}
    actuales = S.resumen(E)["por_clase"]
    objetivo = {c: args.objetivo for c in S.CLASES}
    cuotas = {c: int((objetivo[c] - actuales[c]) / ACIERTO.get(c, 0.5))
              for c in S.CLASES if actuales[c] < objetivo[c]}
    for c in args.clases_extra.split(",") if args.clases_extra else []:
        cuotas[c] = args.cupo_extra      # clases no escasas cuya clase depende de pocos medios
    print("  cupos:", cuotas, "· actuales:", {c: actuales[c] for c in cuotas})

    lados = sorted(set(LADO.values()))
    repetidos = collections.Counter((a.get("source"), a.get("title") or "") for a in bruto.values())
    usados: set[str] = set()
    plan: dict[str, list[dict]] = {}
    for c in sorted(cuotas, key=lambda c: actuales[c]):
        k = clases.index(c)
        tope = args.tope_abs or max(25, int(cuotas[c] * args.tope_fuente))
        orden = {lado: [j for j in np.argsort(-P[:, k])
                        if LADO.get(bruto[ids[j]].get("source")) == lado and P[j, k] >= args.umbral]
                 for lado in lados}
        if args.recientes_desde:
            # Lo reciente primero; dentro de cada bloque sigue el orden por P
            # (sorted es estable). Las clases escasas son 12-26 % de 2026 y el
            # gold 44 %: entrenado sin 2026, el TF-IDF cae 0,06 de macro-F1 en 2026.
            orden = {lado: sorted(v, key=lambda j: S.anio(bruto[ids[j]]) < args.recientes_desde)
                     for lado, v in orden.items()}
        por_fuente: collections.Counter = collections.Counter()
        sel: list[dict] = []
        colas = {lado: iter(v) for lado, v in orden.items()}
        turno = list(lados)
        while len(sel) < cuotas[c] and turno:
            lado = turno.pop(0)
            for j in colas[lado]:
                aid = ids[j]
                fuente = bruto[aid].get("source")
                tn = _titulo_norm(bruto[aid].get("title"))
                if repetidos[(fuente, bruto[aid].get("title") or "")] >= 5:
                    tn = aid     # título genérico del medio: no sirve para detectar duplicados
                if aid in usados or tn in vistos or por_fuente[fuente] >= tope:
                    continue
                sel.append({"id": aid, "p": round(float(P[j, k]), 4), "fuente": fuente,
                            "lado": lado, "argmax": clases[int(P[j].argmax())]})
                usados.add(aid)
                vistos.add(tn)
                por_fuente[fuente] += 1
                turno.append(lado)      # sigue en la rueda mientras le queden
                break
        plan[c] = sel
        reparto = collections.Counter(s["lado"] for s in sel)
        print(f"    {c:<16}{len(sel):6,} / {cuotas[c]:,}  " + str(dict(reparto))
              + f"  fuentes {len(por_fuente)}")

    with CANDIDATOS.open("w", encoding="utf-8") as f:
        for lista in plan.values():
            for s in lista:
                f.write(json.dumps(bruto[s["id"]], ensure_ascii=False) + "\n")
    PLAN.write_text(json.dumps({
        "creado": datetime.now().isoformat(timespec="seconds"), "objetivo": args.objetivo,
        "umbral": args.umbral, "tope_fuente": args.tope_fuente, "cupos": cuotas, "plan": plan,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  ✓ {sum(len(v) for v in plan.values()):,} candidatos → "
          f"{CANDIDATOS.relative_to(ROOT)} · plan {PLAN.relative_to(ROOT)}")


def cmd_filtrar(args: argparse.Namespace) -> None:
    """Politicidad colombiana (Gemini) SOLO sobre los candidatos de la criba.

    Es el mismo filtro del scraper: deja `political_article` y descarta la
    política de otros países (`political_foreign`), que estos medios cubren
    mucho (Palestina, Venezuela) y que el anteproyecto deja fuera.
    """
    import os

    from dotenv import load_dotenv
    from google import genai

    from src.scraper.article_filter import is_real_article
    from src.scraper.pipeline import LLMRateLimiter

    load_dotenv(ROOT / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    limitador = LLMRateLimiter(args.rate_limit)
    hechos = set()
    if FILTRO.exists():
        hechos = {json.loads(x)["id"] for x in FILTRO.open(encoding="utf-8") if x.strip()}
    arts = [json.loads(x) for x in CANDIDATOS.open(encoding="utf-8") if x.strip()]
    pendientes = [a for a in arts if a["id"] not in hechos]
    log(f"filtrar: {len(pendientes):,} pendientes de {len(arts):,}")
    conteo: collections.Counter = collections.Counter()
    for n, a in enumerate(pendientes, 1):
        limitador.wait()
        try:
            ok, info = is_real_article(client, a["text"], rate_limiter=limitador)
        except Exception as exc:  # noqa: BLE001 — se reintenta en la próxima corrida
            log(f"filtrar {a['id']}: {type(exc).__name__} {str(exc)[:80]}")
            time.sleep(30)
            continue
        if info is None:
            continue
        conteo[info.get("category")] += 1
        with FILTRO.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": a["id"], "source": a.get("source"), "pasa": ok,
                                "category": info.get("category"),
                                "confidence": info.get("confidence")}, ensure_ascii=False) + "\n")
        if n % 100 == 0:
            log(f"filtrar {n:,}/{len(pendientes):,} · " + str(dict(conteo.most_common())))
    log("✓ filtrar terminado · " + str(dict(conteo.most_common())))
    exporta_filtrado()


def exporta_filtrado() -> None:
    """El plan de la criba, solo con lo que pasó el filtro: lo que van a juzgar."""
    pasa = {json.loads(x)["id"] for x in FILTRO.open(encoding="utf-8")
            if x.strip() and json.loads(x)["pasa"]}
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    plan["plan"] = {c: [s for s in v if s["id"] in pasa] for c, v in plan["plan"].items()}
    plan["filtrado"] = datetime.now().isoformat(timespec="seconds")
    out = PLAN.with_name(f"{PLAN.stem}_filtrado.json")
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"plan filtrado → {out.relative_to(ROOT)}: " +
        str({c: len(v) for c, v in plan["plan"].items()}))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lote", choices=list(LOTES), default="balance")
    ap.add_argument("--tope", type=int, default=300,
                    help="lote diverso: artículos conservados por medio")
    ap.add_argument("--min-nuevas", type=int, default=150,
                    help="lote diverso: archivo nuevo mínimo para incluir un medio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("descubrir")
    p.add_argument("--fuentes", default=None)
    p.add_argument("--paralelo", type=int, default=8)
    p.add_argument("--force", action="store_true")
    p.add_argument("--recientes", action="store_true", help="ordena las URLs: lo reciente primero")
    p.set_defaults(func=cmd_descubrir)
    p = sub.add_parser("rastrear")
    p.add_argument("--fuentes", default=None)
    p.add_argument("--workers", type=int, default=10)
    p.add_argument("--pausa", type=float, default=1.0, help="segundos entre artículos de una fuente")
    p.add_argument("--min-chars", type=int, default=800)
    p.set_defaults(func=cmd_rastrear)
    p = sub.add_parser("retitular")
    p.add_argument("--min-repetidos", type=int, default=20)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--pausa", type=float, default=0.5)
    p.set_defaults(func=cmd_retitular)
    p = sub.add_parser("cribar")
    p.add_argument("--objetivo", type=int, default=1000, help="etiquetas por clase a alcanzar")
    p.add_argument("--umbral", type=float, default=0.10, help="P mínima de la criba")
    p.add_argument("--tope-fuente", type=float, default=0.15)
    p.add_argument("--tope-abs", type=int, default=0,
                   help="tope de candidatos por medio y clase (gana a --tope-fuente)")
    p.add_argument("--desde", type=int, default=0, help="descarta artículos anteriores a este año")
    p.add_argument("--recientes-desde", type=int, default=0,
                   help="dentro de cada clase, primero los candidatos de este año en adelante")
    p.add_argument("--clases-extra", default="", help="clases no escasas a minar igual (coma)")
    p.add_argument("--cupo-extra", type=int, default=300)
    p.set_defaults(func=cmd_cribar)
    p = sub.add_parser("filtrar")
    p.add_argument("--rate-limit", type=float, default=4.5, help="segundos entre llamadas")
    p.set_defaults(func=cmd_filtrar)
    args = ap.parse_args()
    usa_lote(args.lote, args.tope, args.min_nuevas)
    args.func(args)


if __name__ == "__main__":
    main()
