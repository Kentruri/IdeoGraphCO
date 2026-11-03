"""Tareas del segundo anotador: el gold entero, empezando por lo que el primero ya abrió.

El anteproyecto pide que los DOS investigadores anoten de forma independiente;
sobre lo que anotan ambos se calcula el α de Krippendorff (≥ 0,8) y las
discrepancias se resuelven por consenso. El gold v2 se asignó entero a Juan
(solape 0). Este script le da al segundo anotador los mismos 1.301 artículos.
Van primero los que el primer anotador ya abrió (anotados o saltados), así el
α se puede medir desde el principio, y después el resto en el orden del
primero.

Doble anotación completa y no una muestra: la clase más rara es ~1 % del gold,
y para α mínimo 0,8 con una categoría de esa frecuencia Krippendorff (2019,
fórmula de Bloch y Kraemer 1989) pide ~1.350 unidades con doble anotación.
Además, así cada etiqueta del test sale del acuerdo o el consenso de dos.

NO toca gold_set_v2_ids.json ni gold_set_v2.jsonl: volver a correr
prepare_gold_set.py re-muestrearía el gold y cambiaría el test.

Uso:
    python scripts/gold_solape.py --anotador kevin
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agents.gold import labelstudio  # noqa: E402
from src.core.paths import ROOT  # noqa: E402

ANOTACION = ROOT / "annotation"


def abiertos(export: list[dict]) -> set[str]:
    """IDs de las tareas con alguna anotación, también las saltadas."""
    return {t["data"]["id"] for t in export if t.get("annotations")}


def orden_solape(tareas_primero: list[str], ya_abiertos: set[str]) -> list[str]:
    """Todo el gold: primero lo ya abierto, luego el resto; ambos en el orden del primero."""
    return ([i for i in tareas_primero if i in ya_abiertos]
            + [i for i in tareas_primero if i not in ya_abiertos])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--anotador", required=True, help="nombre del segundo anotador (ej. kevin)")
    ap.add_argument("--primero", default="juan", help="anotador que ya tiene el gold asignado")
    ap.add_argument("--force", action="store_true", help="rehacer unas tareas ya escritas")
    args = ap.parse_args()

    tareas_path = ANOTACION / "labelstudio" / f"gold_set_v2_{args.anotador}_tasks.json"
    if tareas_path.exists() and not args.force:
        raise SystemExit(f"✗ {tareas_path.relative_to(ROOT)} ya existe: cambiarlo a mitad "
                         "de la anotación desordena el trabajo. --force si de verdad hay que rehacerlo.")

    gold_ids = json.loads((ANOTACION / "gold_set_v2_ids.json").read_text(encoding="utf-8"))
    tareas_primero = [t["data"]["id"] for t in json.loads(
        (ANOTACION / "labelstudio" / f"gold_set_v2_{args.primero}_tasks.json").read_text(encoding="utf-8"))]
    if sorted(tareas_primero) != sorted(gold_ids):
        raise SystemExit(f"✗ Las tareas de {args.primero} no son exactamente el gold reservado.")

    export_primero = ANOTACION / f"gold_set_v2_{args.primero}.json"
    ya = abiertos(json.loads(export_primero.read_text(encoding="utf-8"))) if export_primero.exists() else set()
    orden = orden_solape(tareas_primero, ya)

    articulos = {}
    with (ANOTACION / "gold_set_v2.jsonl").open(encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                a = json.loads(linea)
                articulos[a["id"]] = a
    labelstudio.write_tasks([articulos[i] for i in orden], tareas_path)

    asig_path = ANOTACION / "gold_set_v2_assignment.json"
    asig = json.loads(asig_path.read_text(encoding="utf-8"))
    asig["annotators"] = [args.primero, args.anotador]
    asig["overlap_ids"] = orden
    asig["exclusive_ids"] = {args.primero: [], args.anotador: []}
    asig["solape"] = {"fecha": date.today().isoformat(), "modo": "gold completo",
                      "primero_ya_abiertos": len(ya & set(orden))}
    asig_path.write_text(json.dumps(asig, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  {len(orden):,} tareas para {args.anotador}: primero las {len(ya & set(orden))} "
          f"que {args.primero} ya abrió, luego el resto")
    print(f"  ✓ {tareas_path.relative_to(ROOT)}")
    print(f"  ✓ {asig_path.relative_to(ROOT)} (solape: el gold completo)")


if __name__ == "__main__":
    main()
