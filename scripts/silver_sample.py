#!/usr/bin/env python3
"""Plan de muestreo del silver: dirigido por clase, no aleatorio.

El gold (1.301) es una muestra estratificada ALEATORIA: su distribución
sesgada es la del corpus y por eso sirve de test. El silver es el conjunto de
ENTRENAMIENTO, y muestrearlo al azar reproduciría ese sesgo —la calibración
midió ~55 % sin encuadre y 3 doctrinarismo por cada 1.301—, dejando cuatro
clases sin ejemplos suficientes para aprender.

La literatura de clases desbalanceadas recomienda exactamente esta división:
muestra aleatoria apartada para evaluar, selección dirigida para entrenar.

Este script NO etiqueta: propone candidatos por clase puntuando cada artículo
con los marcadores léxicos del codebook, para que el tribunal juzgue una lista
corta en vez de 48.146 artículos. El filtro es de RECALL: prefiere traer de más
y que los jueces descarten, porque un falso positivo cuesta un voto y un falso
negativo cuesta un ejemplo de una clase que casi no tiene.

    python scripts/silver_sample.py --por-clase 900 --aleatorios 2000
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.silver.codebook import AXIS_DEFINITIONS  # noqa: E402
from src.core.paths import RAW_DIR, ROOT  # noqa: E402

GOLD_IDS = ROOT / "annotation" / "gold_set_v2_ids.json"
OUT = ROOT / "data" / "silver" / "plan_muestreo.json"

# Términos demasiado comunes para discriminar: aparecen en casi cualquier nota
# política y solo añadirían ruido al puntaje.
VACIAS = {"de", "la", "el", "los", "las", "y", "o", "en", "que", "del", "al",
          "un", "una", "por", "para", "con", "se", "su", "sus", "como", "es",
          "no", "lo", "a", "ej", "etc", "ante", "sin", "sobre", "entre", "más",
          "texto", "tema", "parte", "forma", "caso", "nivel", "puntaje"}


def normaliza(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# El léxico real de un marcador vive en sus ejemplos —lo entrecomillado y lo
# que va entre paréntesis—, no en la prosa que lo describe. Extraer la frase
# entera metía palabras de codebook ("argumenta", "asunto", "central") que no
# discriminan nada.
_EJEMPLOS = re.compile(r"[“\"']([^”\"']{3,60})[”\"']|\(([^)]{3,200})\)")


def lexico_por_clase() -> dict[str, set[str]]:
    """Términos distintivos de cada clase, de los EJEMPLOS de sus marcadores.

    Un término que aparece en los marcadores de varias clases no discrimina,
    así que se descarta: el objetivo es separar clases, no describirlas.
    """
    crudo: dict[str, set[str]] = {}
    for clase, eje in AXIS_DEFINITIONS.items():
        palabras: set[str] = set()
        for m in eje["markers"]:
            if m.startswith("[TBD"):
                continue
            for cita, parentesis in _EJEMPLOS.findall(m):
                for w in re.findall(r"[a-záéíóúñü]{4,}", normaliza(cita + " " + parentesis)):
                    if w not in VACIAS:
                        palabras.add(w)
            # Sustantivos en mayúscula dentro de la prosa: nombres de
            # entidades y siglas (ONU, OCDE, JEP, Fiscalía) sí discriminan.
            for w in re.findall(r"\b[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]{2,}", m):
                n = normaliza(w)
                if n not in VACIAS and len(n) >= 3:
                    palabras.add(n)
        crudo[clase] = palabras

    frecuencia = collections.Counter(w for ws in crudo.values() for w in ws)
    return {c: {w for w in ws if frecuencia[w] == 1} for c, ws in crudo.items()}


# `doctrinarismo` no se detecta por léxico: la calibración lo encontró solo en
# ensayos largos con aparato de citas ("el género, no las palabras"). Se le da
# un detector propio: densidad de -ismos + teóricos citados + longitud.
_ISMOS = re.compile(r"\b\w{5,}ismo\b")
_TEORICOS = re.compile(
    r"\b(marx|gramsci|weber|habermas|foucault|rousseau|montesquieu|hobbes|"
    r"hayek|keynes|spinoza|arendt|bourdieu|luxemburgo|lenin|schmitt|rawls|"
    r"ortega y gasset|tocqueville|maquiavelo)\b")
_DOCTRINA = re.compile(
    r"\b(doctrina|dogma|ortodoxia|hegemonia|praxis|dialectic\w+|"
    r"materialis\w+|ideari\w+|manifiesto|postulad\w+|axiom\w+)\b")


def puntua_doctrinarismo(texto: str) -> float:
    """Detector de género, no de léxico: ensayo militante con citas."""
    t = normaliza(texto)
    palabras = len(t.split())
    if palabras < 400:          # el ensayo doctrinal no cabe en una nota corta
        return 0.0
    ismos = len(set(_ISMOS.findall(t)))
    teoricos = len(set(_TEORICOS.findall(t)))
    doctrina = len(set(_DOCTRINA.findall(t)))
    if ismos < 2 and teoricos == 0:
        return 0.0
    return (2 * ismos + 5 * teoricos + 3 * doctrina) / math.sqrt(palabras / 400)


def puntua(texto: str, lexico: dict[str, set[str]]) -> dict[str, float]:
    """Densidad de marcadores por clase, normalizada por longitud."""
    palabras = re.findall(r"[a-záéíóúñü]{4,}", normaliza(texto))
    if not palabras:
        return {}
    vistas = collections.Counter(palabras)
    n = len(palabras)
    out = {}
    for clase, terminos in lexico.items():
        golpes = sum(vistas[t] for t in terminos if t in vistas)
        distintos = sum(1 for t in terminos if t in vistas)
        # Los términos DISTINTOS pesan más que la repetición de uno solo:
        # repetir "pueblo" veinte veces no es la dicotomía pueblo/élite.
        out[clase] = (golpes + 3 * distintos) / math.sqrt(n)
    out["doctrinarismo"] = puntua_doctrinarismo(texto)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=None)
    ap.add_argument("--por-clase", type=int, default=900,
                    help="candidatos por clase (el tribunal descartará muchos)")
    ap.add_argument("--aleatorios", type=int, default=2000,
                    help="estrato aleatorio: ancla la prevalencia y pilla lo que el léxico no ve")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    entrada = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    gold = set(json.loads(GOLD_IDS.read_text(encoding="utf-8")))
    lexico = lexico_por_clase()

    print("  Términos distintivos por clase (de sus propios marcadores):")
    for c, t in sorted(lexico.items(), key=lambda kv: -len(kv[1])):
        print(f"    {c:<18} {len(t):3}  {', '.join(sorted(t)[:6])}…")

    mejores: dict[str, list[tuple[float, str]]] = collections.defaultdict(list)
    todos: list[str] = []
    n = 0
    with entrada.open(encoding="utf-8") as f:
        for linea in f:
            if not linea.strip():
                continue
            a = json.loads(linea)
            aid = a.get("id")
            if aid in gold:          # el gold es el test: nunca entra al silver
                continue
            n += 1
            todos.append(aid)
            for clase, s in puntua((a.get("title") or "") + " " + (a.get("text") or ""),
                                   lexico).items():
                if s > 0:
                    mejores[clase].append((s, aid))

    plan: dict[str, list[str]] = {}
    usados: set[str] = set()
    # Las clases escasas eligen primero: si un artículo sirve a dos, va a la
    # que menos ejemplos tiene.
    orden = sorted(AXIS_DEFINITIONS, key=lambda c: len(mejores[c]))
    for clase in orden:
        cands = sorted(mejores[clase], reverse=True)
        sel = [i for _, i in cands if i not in usados][: args.por_clase]
        usados.update(sel)
        plan[clase] = sel

    rng = random.Random(args.seed)
    resto = [i for i in todos if i not in usados]
    rng.shuffle(resto)
    plan["_aleatorio"] = resto[: args.aleatorios]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"corpus": str(entrada), "disponibles": n, "seed": args.seed,
         "por_clase": args.por_clase, "aleatorios": args.aleatorios,
         "plan": plan}, ensure_ascii=False, indent=1), encoding="utf-8")

    total = sum(len(v) for v in plan.values())
    print(f"\n  Disponibles (sin gold): {n:,}")
    print(f"  Plan: {total:,} artículos\n")
    for c, ids in sorted(plan.items(), key=lambda kv: -len(kv[1])):
        print(f"    {c:<18} {len(ids):5}")
    print(f"\n  ✓ {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
