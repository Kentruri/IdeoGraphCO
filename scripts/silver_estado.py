#!/usr/bin/env python3
"""Estado del silver: la etiqueta de cada artículo, reconstruida desde TODOS los votos.

El silver se hizo por rondas, cada una sobre lo que la anterior dejó sin
resolver, y cada ronda escribe sus propios ficheros de votos:

  p1   votos_haiku.jsonl            haiku solo sobre el plan dirigido (9.200), codebook v1.1
  p2   votos_<juez>_sinenc*.jsonl   tres jueces sobre lo que p1 llamó sin_encuadre (+ entonación)
  gem  votos_gemini_*.jsonl         Gemini desempata los p2 sin mayoría
  p3   votos_<juez>_sust*.jsonl     tres jueces sobre lo que p2 dejó en sin_encuadre (+ sustancia)
  r4   votos_<juez>_r4*.jsonl       confirma las etiquetas de un solo juez en clases escasas
                                    y juzga los candidatos minados para balancear

La regla es la misma en todas las rondas de tres jueces: mayoría simple, y se
evalúa PEREZOSA. Si haiku y sonnet coinciden, opus no puede cambiar la mayoría
y no se le pregunta; solo vota cuando discrepan. La etiqueta resultante es la
misma que con los tres votos, a un tercio del coste.

`r4` manda sobre las rondas anteriores: es la única que mira un artículo con el
codebook completo y tres jueces. En una confirmación, el voto de haiku es el
de p1 (mismo modelo; las capas que se añadieron después solo rescatan textos
que p1 llamó sin_encuadre, y estos no lo son).

    python scripts/silver_estado.py            # tabla por clase y vía
    python scripts/silver_estado.py --json     # resumen para otros scripts
    python scripts/silver_estado.py --build    # → data/silver/silver_set.jsonl
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SILVER = ROOT / "data" / "silver"
# De dónde sale el TEXTO de un artículo: el corpus, y los candidatos de cada
# lote del rastreo dirigido (scripts/rastreo_balance.py). Estos no se mezclan
# con el corpus porque de cada lote solo entran las clases que su plan buscaba.
RASTREOS = ((ROOT / "data" / "raw" / "articles_balance.jsonl", SILVER / "plan_balance_filtrado.json"),
            (ROOT / "data" / "raw" / "articles_diverso.jsonl", SILVER / "plan_diverso_filtrado.json"),
            (ROOT / "data" / "raw" / "articles_balance2.jsonl", SILVER / "plan_balance2_filtrado.json"),
            (ROOT / "data" / "raw" / "articles_partidos.jsonl", SILVER / "plan_partidos_filtrado.json"),
            (ROOT / "data" / "raw" / "articles_diverso2.jsonl", SILVER / "plan_diverso2_filtrado.json"),
            (ROOT / "data" / "raw" / "articles_balance3.jsonl", SILVER / "plan_balance3_filtrado.json"))
RAW_FILES = (ROOT / "data" / "raw" / "articles.jsonl", *(raw for raw, _ in RASTREOS))

CLASES = ("populismo", "institucionalismo", "personalismo", "doctrinarismo",
          "soberanismo", "globalismo", "conservadurismo", "progresismo")
NF, DUD = "sin_encuadre", "dud"
JUECES = ("haiku", "sonnet", "opus")

# Estados de un artículo.
UNANIME, MAYORIA, UNICO = "unanime", "mayoria", "unico"
DESEMPATE, DISCREPANCIA = "desempate", "discrepancia"
SIN_ENCUADRE, PENDIENTE = "sin_encuadre", "pendiente"


@dataclass(frozen=True)
class Etiqueta:
    clase: str | None    # una de las ocho, sin_encuadre, o None (sin decisión)
    estado: str
    via: str             # ronda que la fijó
    votos: dict          # {ronda.juez: clase}, para auditar

    @property
    def entrena(self) -> bool:
        """¿Entra al entrenamiento? Solo las ocho clases con voto de verdad."""
        return self.clase in CLASES and self.estado not in (PENDIENTE, DISCREPANCIA)


def _votos(path: Path) -> dict[str, str]:
    """{id: clase}. Gana el último voto; un `dud` cuenta como voto emitido."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for linea in path.open(encoding="utf-8"):
        if not linea.strip():
            continue
        try:
            r = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if r.get("dominant"):
            out[r["id"]] = r["dominant"]
        elif r.get("error") == "duda del anotador":
            out[r["id"]] = DUD
        # cualquier otro fallo (p. ej. error de API) no es un voto
    return out


def _union_en(carpeta: Path, patron: str) -> dict[str, str]:
    """Une los ficheros de un juez en una ronda (los shards de r4, p. ej.)."""
    out: dict[str, str] = {}
    for f in sorted(carpeta.glob(patron)):
        out.update(_votos(f))
    return out


def _union(patron: str) -> dict[str, str]:
    return _union_en(SILVER, patron)


def _ids(corpus: Path) -> set[str]:
    if not corpus.exists():
        return set()
    return {json.loads(x)["id"] for x in corpus.open(encoding="utf-8") if x.strip()}


def _solo(votos: dict[str, str], universo: set[str]) -> dict[str, str]:
    return {i: c for i, c in votos.items() if i in universo}


def cargar() -> dict[str, dict[str, dict[str, str]]]:
    """{ronda: {juez: {id: clase}}}.

    p2 y p3 solo cuentan los votos de SU corpus: haiku dejó 522 votos de p2
    sobre artículos que nunca estuvieron en él (una tanda que arrancó con otro
    fichero), y contarlos dejaba 437 artículos "pendientes" de una ronda a la
    que no pertenecían.
    """
    p2 = _ids(SILVER / "corpus_sinenc.jsonl")
    p3 = _ids(SILVER / "corpus_sustancia.jsonl") | _ids(SILVER / "corpus_sust_decide.jsonl")
    return {
        "p1": {"haiku": _votos(SILVER / "votos_haiku.jsonl")},
        "p2": {j: _solo(_union(f"votos_{j}_sinenc*.jsonl"), p2) for j in JUECES},
        "gem": {"gemini": _union("votos_gemini_*.jsonl")},
        "p3": {j: _solo(_union(f"votos_{j}_sust*.jsonl"), p3) for j in JUECES},
        "r4": {j: _union(f"votos_{j}_r4*.jsonl") for j in JUECES},
    }


def mayoria_perezosa(v: dict[str, str]) -> tuple[str | None, str]:
    """Mayoría de tres evaluada perezosa. `v` = {juez: clase} con lo que haya.

    Devuelve (clase, estado). PENDIENTE si falta un voto que puede decidir.
    """
    h, s, o = v.get("haiku"), v.get("sonnet"), v.get("opus")
    if h is None or s is None:
        return None, PENDIENTE
    if h == s and h != DUD:
        estado = UNANIME if o == h else MAYORIA
        return h, (SIN_ENCUADRE if h == NF else estado)
    if o is None:
        return None, PENDIENTE
    validos = [c for c in (h, s, o) if c != DUD]
    if not validos:
        return None, DISCREPANCIA
    top, n = collections.Counter(validos).most_common(1)[0]
    if n >= 2:
        return top, (SIN_ENCUADRE if top == NF else MAYORIA)
    return None, DISCREPANCIA


def _mayoria_estricta(votos: list[str]) -> tuple[str | None, int]:
    validos = [c for c in votos if c != DUD]
    if not validos:
        return None, 0
    top, n = collections.Counter(validos).most_common(1)[0]
    return (top, n) if n * 2 > len(validos) else (None, n)


def resolver(aid: str, V: dict) -> Etiqueta | None:
    """La etiqueta vigente de un artículo, o None si ninguna ronda lo tocó."""
    p1 = V["p1"]["haiku"].get(aid)
    r4 = {j: V["r4"][j][aid] for j in JUECES if aid in V["r4"][j]}

    if r4:
        votos = dict(r4)
        # Confirmación: el voto de haiku es el de p1, salvo que r4 lo rehiciera.
        if "haiku" not in votos and p1 in CLASES:
            votos["haiku"] = p1
        clase, estado = mayoria_perezosa(votos)
        traza = {f"r4.{j}": c for j, c in r4.items()}
        if p1 is not None:
            traza["p1.haiku"] = p1
        if estado == PENDIENTE and p1 in CLASES:
            # Mientras la confirmación no termina, sigue valiendo la de p1.
            return Etiqueta(p1, UNICO, "p1", traza)
        return Etiqueta(clase, estado, "r4", traza)

    if p1 in CLASES:
        return Etiqueta(p1, UNICO, "p1", {"p1.haiku": p1})

    p2 = {j: V["p2"][j][aid] for j in JUECES if aid in V["p2"][j]}
    if not p2:
        if p1 is None:
            return None
        return Etiqueta(p1 if p1 == NF else None,
                        SIN_ENCUADRE if p1 == NF else DISCREPANCIA, "p1", {"p1.haiku": p1})

    traza = {"p1.haiku": p1, **{f"p2.{j}": c for j, c in p2.items()}}
    if len(p2) < 3:
        return Etiqueta(None, PENDIENTE, "p2", traza)
    m2, n2 = _mayoria_estricta(list(p2.values()))
    if m2 is None:
        g = V["gem"]["gemini"].get(aid)
        if g:
            traza["gem.gemini"] = g
        # Gemini rompe el empate solo si coincide con alguno de los tres.
        if g and g != DUD and list(p2.values()).count(g) == 1:
            return Etiqueta(g, SIN_ENCUADRE if g == NF else DESEMPATE, "p2+gem", traza)
        return Etiqueta(None, DISCREPANCIA, "p2", traza)
    if m2 != NF:
        return Etiqueta(m2, UNANIME if n2 == 3 else MAYORIA, "p2", traza)

    p3 = {j: V["p3"][j][aid] for j in JUECES if aid in V["p3"][j]}
    if not p3:
        return Etiqueta(NF, SIN_ENCUADRE, "p2", traza)
    traza.update({f"p3.{j}": c for j, c in p3.items()})
    clase, estado = mayoria_perezosa(p3)
    return Etiqueta(clase, estado, "p3", traza)


def todas(V: dict | None = None) -> dict[str, Etiqueta]:
    V = V or cargar()
    ids: set[str] = set()
    for ronda in V.values():
        for votos in ronda.values():
            ids.update(votos)
    out = {}
    for aid in ids:
        e = resolver(aid, V)
        if e is not None:
            out[aid] = e
    return out


def resumen(E: dict[str, Etiqueta]) -> dict:
    entrena = collections.Counter(e.clase for e in E.values() if e.entrena)
    return {
        "articulos": len(E),
        "entrenables": sum(entrena.values()),
        "por_clase": {c: entrena.get(c, 0) for c in CLASES},
        "por_estado": dict(collections.Counter(e.estado for e in E.values())),
    }


def iter_raw():
    """Artículos de todas las fuentes de texto, sin repetir id."""
    vistos: set[str] = set()
    for f in RAW_FILES:
        if not f.exists():
            continue
        with f.open(encoding="utf-8") as fin:
            for linea in fin:
                if linea.strip():
                    a = json.loads(linea)
                    if a["id"] not in vistos:
                        vistos.add(a["id"])
                        yield a


def entrenables(E: dict[str, Etiqueta]) -> tuple[list[tuple[dict, Etiqueta]], collections.Counter]:
    """(artículo, etiqueta) de todo lo que entra al silver, y lo que el rastreo deja fuera.

    Los artículos de un lote del rastreo dirigido se bajaron SOLO para las
    clases de su plan: si los jueces les ponen otra (una que ya sobra), no entran.
    """
    permitidas: dict[str, set[str]] = {}
    for raw, plan in RASTREOS:
        if raw.exists() and plan.exists():
            clases = set(json.loads(plan.read_text(encoding="utf-8"))["plan"])
            with raw.open(encoding="utf-8") as f:
                permitidas.update({json.loads(x)["id"]: clases for x in f if x.strip()})
    filas, fuera = [], collections.Counter()
    for a in iter_raw():
        e = E.get(a["id"])
        if e is None or not e.entrena:
            continue
        if a["id"] in permitidas and e.clase not in permitidas[a["id"]]:
            fuera[e.clase] += 1
            continue
        filas.append((a, e))
    return filas, fuera


_FUERZA = {UNANIME: 0, MAYORIA: 1, DESEMPATE: 2, UNICO: 3}


def anio(a: dict) -> int:
    """Año de publicación; 0 si no se sabe."""
    y = str(a.get("date") or "")[:4]
    return int(y) if y.isdigit() else 0


def aplica_topes(filas: list[tuple[dict, Etiqueta]], tope: float, tope_escasas: float,
                 umbral_escasa: int = 1000) -> tuple[list[tuple[dict, Etiqueta]], collections.Counter]:
    """Ningún medio aporta más de `tope` de una clase (`tope_escasas` si la clase es escasa).

    Medido (oct-2026): mincit es el 30 % de globalismo y el 80 % de lo suyo es
    globalismo; contextoganadero, el 20 % de doctrinarismo. El tope es sobre el
    tamaño FINAL de la clase, así que se itera hasta un punto fijo. De un medio
    recortado se quedan los de consenso más fuerte y, a igualdad, los más
    recientes (el gold es 44 % de 2026 y el archivo rastreado es viejo).
    """
    if not tope and not tope_escasas:
        return filas, collections.Counter()
    por_clase: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for a, e in filas:
        por_clase[e.clase][a.get("source") or "?"] += 1
    def punto_fijo(cnt: collections.Counter, f: float) -> int:
        k = int(f * sum(cnt.values()))
        for _ in range(50):
            nuevo = max(1, int(f * sum(min(v, k) for v in cnt.values())))
            if nuevo == k:
                break
            k = nuevo
        return k

    cupo: dict[str, int] = {}
    for c, cnt in por_clase.items():
        # Escasa = la que quedaría bajo el umbral con el tope estricto: si no,
        # el propio tope empujaría bajo el umbral a una clase que apenas lo pasa.
        k = punto_fijo(cnt, tope) if tope else 0
        if not tope or sum(min(v, k) for v in cnt.values()) < umbral_escasa:
            k = punto_fijo(cnt, tope_escasas) if tope_escasas else 0
        if k:
            cupo[c] = k
    orden = sorted(filas, key=lambda x: (_FUERZA.get(x[1].estado, 9), -anio(x[0]), x[0]["id"]))
    usados: collections.Counter = collections.Counter()
    quedan, recortados = set(), collections.Counter()
    for a, e in orden:
        s = a.get("source") or "?"
        if e.clase in cupo and usados[(s, e.clase)] >= cupo[e.clase]:
            recortados[(s, e.clase)] += 1
            continue
        usados[(s, e.clase)] += 1
        quedan.add(a["id"])
    return [(a, e) for a, e in filas if a["id"] in quedan], recortados


def build(E: dict[str, Etiqueta], salida: Path, tope: float = 0.0, tope_escasas: float = 0.0) -> None:
    """Escribe el silver entrenable en el formato de `prepare_splits.py`.

    Entra todo lo que tiene una de las ocho clases con voto real, también las
    etiquetas de un solo juez (`unico`): se marcan en `consensus` para que el
    entrenamiento decida si filtrarlas o ponderarlas, en vez de decidirlo aquí.
    """
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.core.schema import CLASS_TO_IDX

    gold = set(json.loads((ROOT / "annotation" / "gold_set_v2_ids.json").read_text()))
    filas, fuera_rastreo = entrenables(E)
    filas, recortados = aplica_topes(filas, tope, tope_escasas)
    tmp = salida.with_suffix(".jsonl.tmp")
    n = 0
    with tmp.open("w", encoding="utf-8") as fout:
        for a, e in filas:
            if a["id"] in gold:      # el gold es el test: nunca entra al silver
                raise SystemExit(f"✗ {a['id']} es del gold y tiene etiqueta silver.")
            fout.write(json.dumps({
                "id": a["id"], "text": a.get("text", ""), "title": a.get("title", ""),
                "source": a.get("source", ""), "category": a.get("category", ""),
                "url": a.get("url", ""), "date": a.get("date"),
                "label": e.clase, "label_idx": CLASS_TO_IDX[e.clase],
                "label_source": "silver-ensemble",
                "consensus": {"estado": e.estado, "via": e.via, "votos": e.votos,
                              "n_jueces": sum(1 for c in e.votos.values() if c)},
            }, ensure_ascii=False) + "\n")
            n += 1
    tmp.replace(salida)
    print(f"  ✓ {n:,} artículos → {salida.relative_to(ROOT)}")
    if fuera_rastreo:
        print(f"    del rastreo, fuera por no ser de una clase escasa: {dict(fuera_rastreo)}")
    if recortados:
        print(f"    recortados por el tope por medio ({tope:.0%}, escasas {tope_escasas:.0%}): "
              f"{sum(recortados.values()):,}")
        for (s, c), k in recortados.most_common(12):
            print(f"      {s:<24}{c:<18}−{k}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--build", action="store_true",
                    help="escribe data/silver/silver_set.jsonl con lo entrenable")
    ap.add_argument("--tope-medio", type=float, default=0.0,
                    help="--build: fracción máxima de una clase que aporta un medio (0 = sin tope)")
    ap.add_argument("--tope-medio-escasas", type=float, default=0.0,
                    help="--build: lo mismo para las clases con menos de 1.000 ejemplos")
    args = ap.parse_args()

    E = todas()
    if args.json:
        print(json.dumps(resumen(E), ensure_ascii=False, indent=1))
        return
    if args.build:
        build(E, SILVER / "silver_set.jsonl", args.tope_medio, args.tope_medio_escasas)
        return

    tabla = collections.defaultdict(collections.Counter)
    for e in E.values():
        if e.entrena:
            tabla[e.clase][e.estado] += 1
    estados = (UNANIME, MAYORIA, DESEMPATE, UNICO)
    print(f"  {'clase':<18}{'total':>7}" + "".join(f"{s:>12}" for s in estados))
    for c in sorted(CLASES, key=lambda c: -sum(tabla[c].values())):
        fila = tabla[c]
        print(f"  {c:<18}{sum(fila.values()):>7}" + "".join(f"{fila[s]:>12}" for s in estados))
    total = sum(sum(f.values()) for f in tabla.values())
    print(f"  {'TOTAL':<18}{total:>7}")

    print("\n  Fuera del entrenamiento:")
    fuera = collections.Counter((e.estado, e.via) for e in E.values() if not e.entrena)
    for (estado, via), n in fuera.most_common():
        print(f"    {estado:<14} {via:<8} {n:6,}")


if __name__ == "__main__":
    main()
