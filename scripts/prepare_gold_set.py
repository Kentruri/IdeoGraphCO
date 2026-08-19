"""Genera el gold set (Handwrite) para anotación humana — v2 categórico.

Metodología del anteproyecto (Construcción del Corpus):
- Los DOS investigadores anotan DE FORMA INDEPENDIENTE una muestra compartida
  (bloque de solape) → sobre ella se calcula Krippendorff α (umbral 0.8).
- Además de los 8 ejes de intensidad (1-5), cada anotador marca la CLASE
  DOMINANTE (una de las 8) — la etiqueta categórica que consume el clasificador.
- Las discrepancias en la dominante se resuelven por consenso
  (ver scripts/ingest_gold.py).

Salidas:
- annotation/gold_set_v2_<anotador>.xlsx — un libro por anotador
  (solape compartido + bloque exclusivo)
- annotation/gold_set_v2.jsonl — todas las filas muestreadas (link con pipeline)
- annotation/gold_set_v2_ids.json — IDs del gold (excluir de train/val)
- annotation/gold_set_v2_assignment.json — qué IDs son de solape y qué IDs
  corresponden a cada anotador (lo usa ingest_gold.py)

Uso:
    python scripts/prepare_gold_set.py
    python scripts/prepare_gold_set.py --target 200 --overlap 60 --seed 42
    python scripts/prepare_gold_set.py --annotators kevin juan
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

AXES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]

DOMINANT_COL = "clase_dominante"

SCALE_DESC: list[tuple[str, str]] = [
    ("1 — Ausente",   "No hay presencia del marcador."),
    ("2 — Leve",      "Mención puntual, no estructura el argumento."),
    ("3 — Moderado",  "Presencia relevante, balanceada con otros temas."),
    ("4 — Marcado",   "Eje central del discurso, aparece de forma repetida."),
    ("5 — Dominante", "Saturado, todo el mensaje gira en torno a este eje."),
]


def stratified_sample(
    articles: list[dict],
    target: int,
    seed: int = 42,
) -> list[dict]:
    """Muestreo estratificado proporcional por categoría."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for a in articles:
        by_cat[a.get("category", "?")].append(a)

    total = len(articles)
    rng = random.Random(seed)
    samples: list[dict] = []
    for cat, arts in sorted(by_cat.items()):
        n = max(1, round(len(arts) / total * target))
        shuffled = list(arts)
        rng.shuffle(shuffled)
        samples.extend(shuffled[:n])

    rng.shuffle(samples)
    return samples


def build_excel(samples: list[dict], output_path: Path, annotator: str) -> None:
    """Crea el libro de un anotador: instrucciones + artículos para anotar."""
    wb = openpyxl.Workbook()

    # --- Hoja 1: Instrucciones ---
    ws_help = wb.active
    ws_help.title = "Instrucciones"

    bold = Font(bold=True, size=12)
    big = Font(bold=True, size=14)

    ws_help["A1"] = f"Bitácora de anotación — IdeoGraphCO (anotador: {annotator})"
    ws_help["A1"].font = big
    ws_help.merge_cells("A1:C1")

    ws_help["A3"] = "Tarea"
    ws_help["A3"].font = bold
    ws_help["A4"] = (
        "Para cada artículo: (1) califica con un entero del 1 al 5 cada uno de "
        "los 8 ejes ideológicos, y (2) marca la CLASE DOMINANTE — obligatoria — "
        "la ideología cuyo encuadre ESTRUCTURA el argumento del texto. Todos los "
        "artículos ya pasaron el filtro de politicidad — asume que son políticos. "
        "Anota SOLO tu libro, de forma independiente: no compares respuestas con "
        "el otro anotador hasta terminar (la concordancia α se calcula sobre el "
        "bloque compartido)."
    )
    ws_help["A4"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_help.row_dimensions[4].height = 90

    ws_help["A6"] = "Escala (igual al codebook del PDF)"
    ws_help["A6"].font = bold
    for i, (lvl, desc) in enumerate(SCALE_DESC, start=7):
        ws_help[f"A{i}"] = lvl
        ws_help[f"B{i}"] = desc
        ws_help[f"A{i}"].font = Font(bold=True)

    ws_help["A14"] = "8 ejes ideológicos"
    ws_help["A14"].font = bold
    ejes_doc: list[tuple[str, str]] = [
        ("Personalismo", "Líder individual como eje central, retórica carismática."),
        ("Institucionalismo", "Instituciones, leyes, procesos formales como ejes."),
        ("Populismo", "Dicotomía pueblo vs. élite, apelación a la voluntad popular."),
        ("Doctrinarismo", "Cuerpo ideológico rígido como argumento de autoridad."),
        ("Soberanismo", "Autonomía nacional, rechazo a injerencia externa."),
        ("Globalismo", "Cooperación internacional, normas globales, multilateralismo."),
        ("Conservadurismo", "Tradición, orden, propiedad, autoridad, mano dura."),
        ("Progresismo", "Justicia social, derechos de minorías, reformas estructurales."),
    ]
    for i, (eje, desc) in enumerate(ejes_doc, start=15):
        ws_help[f"A{i}"] = eje
        ws_help[f"B{i}"] = desc
        ws_help[f"A{i}"].font = Font(bold=True)

    ws_help["A24"] = "Reglas clave"
    ws_help["A24"].font = bold
    rules = [
        "Evalúa solo lo que el texto dice explícitamente, no asumas postura por el medio.",
        "Los 8 ejes de intensidad son INDEPENDIENTES. No tienen que sumar nada.",
        "Los pares opuestos NO son excluyentes en intensidad (un texto puede ser alto en ambos).",
        "Las escalas miden INTENSIDAD del marcador, no si el autor está a favor o en contra.",
        "clase_dominante es OBLIGATORIA y única: el marco que estructura el argumento "
        "(¿qué retórica organiza el titular y el primer tercio del texto, en la voz "
        "propia del texto?). Si dos empatan, elige la que motivaría el titular.",
        "Si dudas en un eje, déjalo vacío y completa al final con calma.",
    ]
    for i, r in enumerate(rules, start=25):
        ws_help[f"A{i}"] = f"• {r}"
        ws_help[f"A{i}"].alignment = Alignment(wrap_text=True)
        ws_help.row_dimensions[i].height = 30

    ws_help.column_dimensions["A"].width = 30
    ws_help.column_dimensions["B"].width = 90

    # --- Hoja 2: Artículos ---
    ws = wb.create_sheet("Articulos")

    headers = (
        ["id", "source", "category", "url", "title", "text"]
        + AXES
        + [DOMINANT_COL, "notes"]
    )
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Resaltar la columna obligatoria
    dominant_idx = 7 + len(AXES)  # 1-based
    ws.cell(row=1, column=dominant_idx).fill = PatternFill("solid", fgColor="FFE59A")

    for a in samples:
        ws.append([
            a.get("id", ""),  # ID estable (sha256(url)[:16])
            a.get("source", ""),
            a.get("category", ""),
            a.get("url", ""),
            a.get("title", ""),
            a.get("text", ""),
            *[None] * len(AXES),  # ejes (anotador llena)
            None,  # clase_dominante (anotador llena — OBLIGATORIA)
            None,  # notes
        ])

    widths = {
        "A": 18,  # id
        "B": 14,  # source
        "C": 14,  # category
        "D": 40,  # url
        "E": 40,  # title
        "F": 80,  # text
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for col_idx in range(7, 7 + len(AXES)):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16
    ws.column_dimensions[get_column_letter(dominant_idx)].width = 20
    ws.column_dimensions[get_column_letter(dominant_idx + 1)].width = 30

    notes_col = get_column_letter(dominant_idx + 1)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            if cell.column_letter in ("E", "F", notes_col):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                cell.alignment = Alignment(vertical="top", horizontal="center")

    ws.freeze_panes = "G2"

    # Data validation: ejes 1-5
    dv_axes = DataValidation(
        type="list", formula1='"1,2,3,4,5"', allow_blank=True,
        showErrorMessage=True, errorTitle="Valor inválido",
        error="Solo entero 1, 2, 3, 4 o 5.",
    )
    first_axis_col = get_column_letter(7)
    last_axis_col = get_column_letter(7 + len(AXES) - 1)
    dv_axes.add(f"{first_axis_col}2:{last_axis_col}{ws.max_row}")
    ws.add_data_validation(dv_axes)

    # Data validation: clase dominante (una de las 8)
    dv_dominant = DataValidation(
        type="list", formula1=f'"{",".join(AXES)}"', allow_blank=True,
        showErrorMessage=True, errorTitle="Clase inválida",
        error="Debe ser una de las 8 clases (en minúsculas).",
    )
    dom_col_letter = get_column_letter(dominant_idx)
    dv_dominant.add(f"{dom_col_letter}2:{dom_col_letter}{ws.max_row}")
    ws.add_data_validation(dv_dominant)

    wb.save(output_path)


def assign_books(
    samples: list[dict],
    annotators: list[str],
    overlap: int,
) -> tuple[dict[str, list[dict]], dict]:
    """Reparte artículos: bloque de solape (todos los anotadores) + exclusivos.

    El solape es lo que permite calcular Krippendorff α; los exclusivos
    amplían la cobertura del gold sin duplicar esfuerzo.
    """
    overlap = min(overlap, len(samples))
    overlap_block = samples[:overlap]
    rest = samples[overlap:]

    books: dict[str, list[dict]] = {name: list(overlap_block) for name in annotators}
    exclusive: dict[str, list[str]] = {name: [] for name in annotators}
    for i, article in enumerate(rest):
        owner = annotators[i % len(annotators)]
        books[owner].append(article)
        exclusive[owner].append(article["id"])

    assignment = {
        "annotators": annotators,
        "overlap_ids": [a["id"] for a in overlap_block],
        "exclusive_ids": exclusive,
    }
    return books, assignment


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera gold set humano v2 (Excel)")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL de artículos (default: data/raw/articles.jsonl)",
    )
    parser.add_argument(
        "--target", type=int, default=200,
        help="Cantidad de artículos ÚNICOS a muestrear (default: 200)",
    )
    parser.add_argument(
        "--overlap", type=int, default=60,
        help="Artículos del bloque compartido para Krippendorff α (default: 60)",
    )
    parser.add_argument(
        "--annotators", nargs="+", default=["anotador1", "anotador2"],
        help="Nombres de los anotadores (default: anotador1 anotador2)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Semilla para reproducibilidad (default: 42)",
    )
    parser.add_argument(
        "--version", type=str, default="v2",
        help="Sufijo de versión de los archivos (default: v2)",
    )
    args = parser.parse_args()

    from src.core.paths import RAW_DIR, ROOT

    input_path = Path(args.input) if args.input else RAW_DIR / "articles.jsonl"
    annotation_dir = ROOT / "annotation"
    annotation_dir.mkdir(parents=True, exist_ok=True)

    base = f"gold_set_{args.version}"
    output_jsonl = annotation_dir / f"{base}.jsonl"
    output_ids = annotation_dir / f"{base}_ids.json"
    output_assignment = annotation_dir / f"{base}_assignment.json"

    if not input_path.exists():
        print(f"✗ No existe {input_path}")
        return

    with open(input_path, encoding="utf-8") as f:
        articles = [json.loads(line) for line in f if line.strip()]

    print(f"Cargados {len(articles)} artículos de {input_path}")

    samples = stratified_sample(articles, target=args.target, seed=args.seed)

    from collections import Counter
    cat_count = Counter(a.get("category", "?") for a in samples)
    print(f"\nMuestreo estratificado ({len(samples)} artículos, semilla={args.seed}):")
    for cat, c in cat_count.most_common():
        print(f"  {cat:15} {c:3d}")

    books, assignment = assign_books(samples, args.annotators, args.overlap)

    print(f"\nSolape (α): {len(assignment['overlap_ids'])} artículos anotados por todos")
    for name in args.annotators:
        n_total = len(books[name])
        n_excl = len(assignment["exclusive_ids"][name])
        output_xlsx = annotation_dir / f"{base}_{name}.xlsx"
        build_excel(books[name], output_xlsx, annotator=name)
        print(f"✓ {name}: {output_xlsx.name} ({n_total} artículos: "
              f"{len(assignment['overlap_ids'])} solape + {n_excl} exclusivos)")

    with open(output_jsonl, "w", encoding="utf-8") as f:
        for a in samples:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"✓ JSONL: {output_jsonl}")

    ids = [a["id"] for a in samples]
    with open(output_ids, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    print(f"✓ IDs:   {output_ids}")

    with open(output_assignment, "w", encoding="utf-8") as f:
        json.dump(assignment, f, ensure_ascii=False, indent=2)
    print(f"✓ Asignación: {output_assignment}")

    print(
        "\nSiguiente paso (cuando terminen de anotar):\n"
        "  python scripts/ingest_gold.py --books "
        + " ".join(f"annotation/{base}_{n}.xlsx" for n in args.annotators)
    )


if __name__ == "__main__":
    main()
