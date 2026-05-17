"""Genera el gold set para anotación humana.

Hace muestreo estratificado proporcional por categoría sobre el JSONL filtrado y
exporta:
- annotation/gold_set_v1.xlsx — Excel para que los anotadores llenen a mano
- annotation/gold_set_v1.jsonl — Mismas filas en JSONL (link con el pipeline)
- annotation/gold_set_v1_ids.json — Lista de URLs/IDs del gold (para excluir del
  pool de train/val cuando se preparen splits)

El Excel incluye:
- Hoja "Instrucciones": resumen del codebook y escala 1-5
- Hoja "Articulos": 1 fila por artículo, columnas para is_political + 8 ejes
- Validación de datos: is_political ∈ {0,1}, ejes ∈ {1,2,3,4,5}

Uso:
    python scripts/prepare_gold_set.py
    python scripts/prepare_gold_set.py --target 200 --seed 42
    python scripts/prepare_gold_set.py --target 100 --output annotation/gold_v2.xlsx
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


def build_excel(samples: list[dict], output_path: Path) -> None:
    """Crea el Excel con dos hojas: instrucciones y artículos para anotar."""
    wb = openpyxl.Workbook()

    # --- Hoja 1: Instrucciones ---
    ws_help = wb.active
    ws_help.title = "Instrucciones"

    bold = Font(bold=True, size=12)
    big = Font(bold=True, size=14)

    ws_help["A1"] = "Bitácora de anotación — IdeoGraphCO"
    ws_help["A1"].font = big
    ws_help.merge_cells("A1:C1")

    ws_help["A3"] = "Tarea"
    ws_help["A3"].font = bold
    ws_help["A4"] = (
        "Lee cada artículo y califica con un entero del 1 al 5 cada uno de "
        "los 8 ejes ideológicos. Si NO es político, marca is_political=0 y "
        "los 8 ejes en 1 (Ausente)."
    )
    ws_help["A4"].alignment = Alignment(wrap_text=True, vertical="top")
    ws_help.row_dimensions[4].height = 60

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
        "Los 8 ejes son INDEPENDIENTES. No tienen que sumar nada.",
        "Los pares opuestos NO son excluyentes (un texto puede ser alto en ambos).",
        "Mide INTENSIDAD del marcador, no si el autor está a favor o en contra.",
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

    # Headers
    headers = (
        ["id", "source", "category", "url", "title", "text", "is_political"]
        + AXES
        + ["notes"]
    )
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
        cell.alignment = Alignment(horizontal="center", vertical="center")

    # Filas
    for a in samples:
        ws.append([
            a.get("id", ""),  # ID estable (sha256(url)[:16])
            a.get("source", ""),
            a.get("category", ""),
            a.get("url", ""),
            a.get("title", ""),
            a.get("text", ""),
            None,  # is_political (anotador llena)
            *[None] * len(AXES),  # ejes (anotador llena)
            None,  # notes
        ])

    # Anchos de columnas
    widths = {
        "A": 18,  # id (16 hex chars + margen)
        "B": 14,  # source
        "C": 14,  # category
        "D": 40,  # url
        "E": 40,  # title
        "F": 80,  # text
        "G": 12,  # is_political
    }
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    # Ejes (H..O) y notes (P)
    for col_idx in range(8, 8 + len(AXES)):
        ws.column_dimensions[get_column_letter(col_idx)].width = 16
    ws.column_dimensions[get_column_letter(8 + len(AXES))].width = 30

    # Wrap text en text, title, notes
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for cell in row:
            if cell.column_letter in ("E", "F", "P"):
                cell.alignment = Alignment(wrap_text=True, vertical="top")
            else:
                cell.alignment = Alignment(vertical="top", horizontal="center")

    # Freeze: primera fila + columnas hasta text
    ws.freeze_panes = "G2"

    # Data validation: is_political ∈ {0,1}, ejes ∈ {1..5}
    dv_pol = DataValidation(
        type="list", formula1='"0,1"', allow_blank=True,
        showErrorMessage=True, errorTitle="Valor inválido", error="Solo 0 o 1.",
    )
    dv_pol.add(f"G2:G{ws.max_row}")
    ws.add_data_validation(dv_pol)

    dv_axes = DataValidation(
        type="list", formula1='"1,2,3,4,5"', allow_blank=True,
        showErrorMessage=True, errorTitle="Valor inválido",
        error="Solo entero 1, 2, 3, 4 o 5.",
    )
    first_axis_col = get_column_letter(8)
    last_axis_col = get_column_letter(8 + len(AXES) - 1)
    dv_axes.add(f"{first_axis_col}2:{last_axis_col}{ws.max_row}")
    ws.add_data_validation(dv_axes)

    wb.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera gold set humano (Excel)")
    parser.add_argument(
        "--input", type=str, default=None,
        help="JSONL filtrado (default: data/raw/news_filtered.jsonl)",
    )
    parser.add_argument(
        "--target", type=int, default=200,
        help="Cantidad de artículos a muestrear (default: 200)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Semilla para reproducibilidad (default: 42)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Path del Excel (default: annotation/gold_set_v1.xlsx)",
    )
    args = parser.parse_args()

    from src.paths import RAW_DIR, ROOT

    input_path = Path(args.input) if args.input else RAW_DIR / "news_filtered.jsonl"
    annotation_dir = ROOT / "annotation"
    annotation_dir.mkdir(parents=True, exist_ok=True)

    output_xlsx = Path(args.output) if args.output else annotation_dir / "gold_set_v1.xlsx"
    output_jsonl = output_xlsx.with_suffix(".jsonl")
    output_ids = output_xlsx.parent / (output_xlsx.stem + "_ids.json")

    if not input_path.exists():
        print(f"✗ No existe {input_path}")
        return

    with open(input_path, encoding="utf-8") as f:
        articles = [json.loads(line) for line in f if line.strip()]

    print(f"Cargados {len(articles)} artículos de {input_path}")

    samples = stratified_sample(articles, target=args.target, seed=args.seed)

    # Reportar distribución del muestreo
    from collections import Counter
    cat_count = Counter(a.get("category", "?") for a in samples)
    print(f"\nMuestreo estratificado ({len(samples)} artículos, semilla={args.seed}):")
    for cat, c in cat_count.most_common():
        print(f"  {cat:15} {c:3d}")

    # Excel
    build_excel(samples, output_xlsx)
    print(f"\n✓ Excel: {output_xlsx}")

    # JSONL paralelo
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for a in samples:
            f.write(json.dumps(a, ensure_ascii=False) + "\n")
    print(f"✓ JSONL: {output_jsonl}")

    # IDs estables (para excluir del pool de train/val después).
    # Estos IDs son hashes deterministas del URL: misma URL → mismo id.
    ids = [a["id"] for a in samples]
    with open(output_ids, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)
    print(f"✓ IDs:   {output_ids}")


if __name__ == "__main__":
    main()
