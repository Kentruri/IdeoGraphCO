"""Empaqueta todo lo que un anotador necesita, en un solo archivo .zip.

Para ANOTAR no hace falta el corpus (641 MB) ni clonar el repo: bastan las
tareas del gold (unos 5 MB) y la plantilla de la interfaz. Por eso esto no
pasa por DVC ni por Hugging Face — se manda por Drive, correo o WhatsApp y el
anotador solo instala Label Studio.

El paquete lleva:
  - <nombre>_tasks.json      las tareas, ciegas (sin medio, categoría ni URL)
  - labeling_config.xml      la interfaz de anotación
  - LEEME.md                 los cuatro comandos, escritos para quien no
                             conoce el proyecto

Uso:
    python scripts/package_for_annotator.py --annotator juan
    python scripts/package_for_annotator.py --annotator juan --limit 400
"""

import argparse
import csv
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.gold import labelstudio  # noqa: E402

ANNOTATION_DIR = ROOT / "annotation"
OUT_DIR = ROOT / "annotation" / "paquetes"


def _readme(annotator: str, n: int) -> str:
    return f"""# Anotación del gold set — IdeoGraphCO

{n:,} artículos de prensa política colombiana. Hay que asignarle a cada uno
**una** de las ocho clases ideológicas: la que ESTRUCTURA el argumento del
texto, no la que se menciona de pasada.

No verás el medio ni la sección del artículo: es a propósito, para juzgar por
el texto y no por su origen.

## 1. Instalar Label Studio (una vez)

Necesita Python 3.10 o superior.

```bash
python3 -m venv ~/label-studio-env
~/label-studio-env/bin/pip install label-studio
```

## 2. Arrancarlo

```bash
~/label-studio-env/bin/label-studio start --port 8080
```

Se abre `http://localhost:8080`. Crea una cuenta (correo y contraseña
cualesquiera: solo existen en tu computador).

## 3. Crear el proyecto

1. **Create Project** → nombre: `Gold set — {annotator}`
2. Pestaña **Labeling Setup** → `Custom template` → borra lo que haya y pega
   el contenido de `labeling_config.xml`
3. Pestaña **Data Import** → sube `{annotator}_tasks.json`
4. **Save**

## 4. Anotar

Un artículo por pantalla: se lee a la izquierda, se elige la clase a la
derecha, `Submit`, y pasa al siguiente.

- La clase es **obligatoria**; sin ella no deja enviar.
- Usa el campo de **notas** cuando dudes o cuando dos clases empaten. Esas
  notas sirven después para revisar los casos difíciles.
- No hace falta terminarlo de una sentada: se guarda solo y puedes cerrar y
  volver cuando quieras.
- En **Projects → tu proyecto** hay una tabla con los {n:,} artículos, cuántos
  llevas y qué le pusiste a cada uno. Puedes filtrar por "sin anotar" para
  ver lo que falta, y volver a cualquiera para cambiar tu decisión.

## 5. Entregar

Cuando lleves un bloque (o al terminar):

**Export → JSON** — el formato completo, **NO** el `JSON-MIN` — y mándale el
archivo a Kevin.

Puedes exportar tantas veces como quieras: cada export incluye todo lo
anotado hasta ese momento.

## Las ocho clases

Van en cuatro ejes opuestos:

| Eje | Clases |
|---|---|
| Gobernanza y discurso | populismo ↔ institucionalismo |
| Liderazgo político | personalismo ↔ doctrinarismo |
| Política exterior | soberanismo ↔ globalismo |
| Sociocultural | conservadurismo ↔ progresismo |

La interfaz muestra una pista corta bajo cada una. Para los criterios
detallados, usa el codebook que acordaste con Kevin.
"""


# Excel corta las celdas a 32.767 caracteres; Google Sheets, a 50.000. El
# texto se escribe ENTERO: recortarlo haría que el anotador decidiera sobre un
# artículo mutilado sin saberlo. Solo se avisa de cuántos afectaría en Excel.
_EXCEL_CELL_LIMIT = 32767
_SHEETS_CELL_LIMIT = 50000

CSV_COLUMNS = ["n", "id", "titulo", "texto", "clase", "notas"]

_CSV_README = """Anotacion del gold set - IdeoGraphCO
=====================================

{n} articulos de prensa politica colombiana.

QUE HAY QUE HACER
-----------------
Para cada fila, escribir en la columna "clase" UNA de estas ocho:

  populismo           institucionalismo
  personalismo        doctrinarismo
  soberanismo         globalismo
  conservadurismo     progresismo

Es la clase que ESTRUCTURA el argumento del texto, no la que se menciona de
pasada. Si dudas o dos clases empatan, escribelo en la columna "notas": esos
casos se revisan despues.

No aparece el medio ni la seccion del articulo: es a proposito, para juzgar
por el texto y no por su origen.

COMO ABRIRLO
------------
Recomendado: Google Sheets (Archivo > Importar > Subir). Cabe todo.

Si lo abres en Excel, {excel} articulos muy largos se veran cortados (Excel no
admite celdas de mas de 32.767 caracteres). En Google Sheets no pasa.

No hace falta terminarlo de una vez: se puede ir llenando por partes. Las
filas estan en orden variado a proposito, asi que si solo llenas las primeras
200 siguen siendo una muestra representativa.

COMO ENTREGARLO
---------------
Descargar como CSV (Archivo > Descargar > .csv) y mandarselo a Kevin.

NO cambiar el orden de las filas ni la columna "id": es lo que permite
enlazar cada respuesta con su articulo.
"""


def _write_csv(articles: list[dict], path: Path) -> tuple[int, int]:
    """Escribe el CSV de anotacion. Devuelve (filas, textos largos)."""
    largos = 0
    # utf-8-sig: sin el BOM, Excel destroza los acentos al abrir el CSV.
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for n, article in enumerate(articles, start=1):
            texto = article.get("text", "") or ""
            if len(texto) > _EXCEL_CELL_LIMIT:
                largos += 1
            writer.writerow({
                "n": n,
                "id": article["id"],
                "titulo": (article.get("title") or "").strip(),
                "texto": texto,
                "clase": "",
                "notas": "",
            })
    return len(articles), largos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Empaqueta el gold set para un anotador")
    parser.add_argument("--annotator", type=str, required=True)
    parser.add_argument("--version", type=str, default="v2")
    parser.add_argument("--limit", type=int, default=None,
                        help="Solo los primeros N artículos")
    parser.add_argument("--input", type=str, default=None,
                        help="JSONL del gold (default: annotation/gold_set_<v>.jsonl)")
    parser.add_argument("--format", choices=["labelstudio", "csv"],
                        default="labelstudio",
                        help="labelstudio: tareas + interfaz (recomendado). "
                             "csv: una hoja de calculo para llenar a mano")
    args = parser.parse_args()

    src = Path(args.input) if args.input else \
        ANNOTATION_DIR / f"gold_set_{args.version}.jsonl"
    if not src.exists():
        raise SystemExit(
            f"✗ No existe {src}\n"
            "  Genera el gold primero:  python scripts/prepare_gold_set.py")

    articles = [json.loads(line) for line in
                open(src, encoding="utf-8") if line.strip()]
    if args.limit:
        articles = articles[:args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        csv_path = OUT_DIR / f"anotacion_{args.annotator}_{args.version}.csv"
        filas, largos = _write_csv(articles, csv_path)
        readme = OUT_DIR / f"LEEME_{args.annotator}.txt"
        readme.write_text(_CSV_README.format(n=f"{filas:,}", excel=largos),
                          encoding="utf-8")
        print(f"✓ {csv_path.relative_to(ROOT)}  "
              f"({csv_path.stat().st_size/1e6:.1f} MB · {filas:,} filas)")
        print(f"✓ {readme.relative_to(ROOT)}")
        if largos:
            print(f"\n  ⚠ {largos} artículos pasan de 32.767 caracteres: Excel los")
            print("    cortaría. En Google Sheets caben enteros — dile que lo abra ahí.")
        print("\n  Cuando te devuelva el CSV lleno:")
        print("    .venv/bin/python scripts/ingest_gold.py --books <archivo.csv>")
        return

    tasks = labelstudio.build_tasks(articles)
    config = labelstudio.build_labeling_config()

    zip_path = OUT_DIR / f"anotacion_{args.annotator}_{args.version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{args.annotator}_tasks.json",
                   json.dumps(tasks, ensure_ascii=False))
        z.writestr("labeling_config.xml", config)
        z.writestr("LEEME.md", _readme(args.annotator, len(tasks)))

    size = zip_path.stat().st_size
    print(f"✓ {zip_path.relative_to(ROOT)}  ({size/1e6:.1f} MB)")
    print(f"  {len(tasks):,} artículos · interfaz + instrucciones incluidas")
    print()
    print("  Mándaselo por Drive, correo o WhatsApp: no necesita el corpus")
    print("  (641 MB) ni clonar el repositorio para anotar.")
    print()
    print("  Cuando te devuelva su export JSON:")
    print(f"    mv <archivo> annotation/gold_set_{args.version}_{args.annotator}.json")
    print(f"    .venv/bin/python scripts/ingest_gold.py --books "
          f"annotation/gold_set_{args.version}_{args.annotator}.json")


if __name__ == "__main__":
    main()
