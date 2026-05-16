"""Genera Excel de muestra con 200 artículos por ideología para el director.

Lee data/interim/labeled_news.jsonl, selecciona top N artículos por cada eje
ideológico y exporta a un Excel con 8 hojas (una por ideología).

Uso:
    python scripts/generate_sample.py
    python scripts/generate_sample.py --top 200 --output muestra.xlsx
"""

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.paths import INTERIM_DIR, ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

AXES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]


def load_labeled_articles(path: Path) -> list[dict]:
    """Carga el archivo JSONL de artículos etiquetados (solo políticos)."""
    articles = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            if data.get("is_political") == 1:
                articles.append(data)
    return articles


def build_sheet(articles: list[dict], axis: str, top_n: int) -> pd.DataFrame:
    """Construye DataFrame con top N artículos del eje, ordenados por score."""
    sorted_articles = sorted(articles, key=lambda a: a[axis], reverse=True)[:top_n]

    rows = []
    for a in sorted_articles:
        # Eje principal del artículo (el de mayor score)
        principal = max(AXES, key=lambda ax: a[ax])

        rows.append({
            "IDEOLOGIA": f"[{axis.upper()}]",
            "SCORE_PRINCIPAL": round(a[axis] * 100),
            "IDEOLOGIA_TOP_GENERAL": f"[{principal.upper()}]",
            "TITULO": a.get("title", ""),
            "TEXTO": a["text"],
            "FUENTE": a.get("source", ""),
            "CATEGORIA_FUENTE": a.get("category", ""),
            "URL": a.get("url", ""),
            "FECHA": a.get("date", ""),
            # Todos los porcentajes
            "%_PERSONALISMO": round(a["personalismo"] * 100),
            "%_INSTITUCIONALISMO": round(a["institucionalismo"] * 100),
            "%_POPULISMO": round(a["populismo"] * 100),
            "%_DOCTRINARISMO": round(a["doctrinarismo"] * 100),
            "%_SOBERANISMO": round(a["soberanismo"] * 100),
            "%_GLOBALISMO": round(a["globalismo"] * 100),
            "%_CONSERVADURISMO": round(a["conservadurismo"] * 100),
            "%_PROGRESISMO": round(a["progresismo"] * 100),
        })
    return pd.DataFrame(rows)


def build_summary(articles: list[dict], top_n: int) -> pd.DataFrame:
    """Hoja resumen con estadísticas por eje."""
    rows = []
    for axis in AXES:
        scores = [a[axis] for a in articles]
        over_50 = sum(1 for s in scores if s >= 0.5)
        over_70 = sum(1 for s in scores if s >= 0.7)
        top = sorted(scores, reverse=True)[:top_n]
        avg_top = sum(top) / len(top) if top else 0
        rows.append({
            "IDEOLOGIA": axis.capitalize(),
            "ARTICULOS_SCORE_>=_50": over_50,
            "ARTICULOS_SCORE_>=_70": over_70,
            f"PROMEDIO_TOP_{top_n}": round(avg_top * 100, 1),
            "MIN_TOP_200": round(top[-1] * 100, 1) if top else 0,
            "MAX_TOP_200": round(top[0] * 100, 1) if top else 0,
        })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera Excel de muestra para el director")
    parser.add_argument("--top", type=int, default=200,
                        help="Top N artículos por ideología (default: 200)")
    parser.add_argument("--input", type=str, default=None,
                        help="JSONL etiquetado (default: data/interim/labeled_news.jsonl)")
    parser.add_argument("--output", type=str, default=None,
                        help="Archivo Excel de salida (default: muestra_ideologica.xlsx)")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else INTERIM_DIR / "labeled_news.jsonl"
    output_path = Path(args.output) if args.output else ROOT / "muestra_ideologica.xlsx"

    logger.info("Cargando artículos de %s", input_path)
    articles = load_labeled_articles(input_path)
    logger.info("Total artículos políticos: %d", len(articles))

    if len(articles) == 0:
        logger.error("No hay artículos políticos. ¿Corriste el etiquetado?")
        return

    logger.info("Generando Excel con top %d por ideología...", args.top)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Hoja resumen
        summary = build_summary(articles, args.top)
        summary.to_excel(writer, sheet_name="RESUMEN", index=False)

        # Una hoja por ideología
        for axis in AXES:
            df = build_sheet(articles, axis, args.top)
            sheet_name = axis.upper()[:31]  # Excel limita a 31 chars
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            logger.info("  %s: %d filas (score min: %.0f%%, max: %.0f%%)",
                        axis, len(df),
                        df["SCORE_PRINCIPAL"].min(), df["SCORE_PRINCIPAL"].max())

    logger.info("Excel guardado en: %s", output_path)
    logger.info("  Total filas (artículo-ideología): %d", len(AXES) * args.top)
    logger.info("  Hojas: RESUMEN + %d por ideología", len(AXES))


if __name__ == "__main__":
    main()
