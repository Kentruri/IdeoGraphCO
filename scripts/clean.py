"""Limpieza y filtrado de artículos scrapeados.

Lee data/raw/news.jsonl, filtra secciones no políticas, limpia el texto
y guarda en data/raw/news_clean.jsonl.
Usa un cursor (.clean_cursor) para no reprocesar artículos ya limpiados.

Uso:
    python scripts/clean.py
    python scripts/clean.py --force           # re-limpia todo desde cero
    python scripts/clean.py --no-filter       # no filtra por sección (mantiene todo)
"""

import argparse
import json
import logging
from urllib.parse import urlparse

from src.data.scraping.cleaner import clean_article_text
from src.paths import RAW_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

INPUT_PATH = RAW_DIR / "news.jsonl"
OUTPUT_PATH = RAW_DIR / "news_clean.jsonl"
CURSOR_PATH = RAW_DIR / ".clean_cursor"

# ---------------------------------------------------------------------------
# Secciones de URL que son claramente NO políticas (ruido para el modelo)
# ---------------------------------------------------------------------------

NOISE_SECTIONS: set[str] = {
    "deportes", "deporte", "futbol", "liga",
    "entretenimiento", "farandula", "gente", "celebridades",
    "tecnologia", "tech", "gadgets", "videojuegos",
    "loterias", "horoscopo", "astrologia",
    "turismo", "viajes", "destinos",
    "recetas", "cocina", "gastronomia",
    "moda", "belleza", "estilo",
    "autos", "carros", "motos",
    "podcasts", "multimedia", "en-vivo", "videos",
    "ocio", "juegos",
    "salud", "bienestar",
    "cine", "musica", "television",
    "contenido-patrocinado", "branded-content",
}


def _get_url_section(url: str) -> str:
    """Extrae la primera sección de la ruta de una URL."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    return parts[0].lower() if parts and parts[0] else "root"


def _is_noise_section(url: str) -> bool:
    """Verifica si un artículo pertenece a una sección no política."""
    section = _get_url_section(url)
    return section in NOISE_SECTIONS


def read_cursor() -> int:
    """Lee la última línea procesada (0 si no hay cursor)."""
    if CURSOR_PATH.exists():
        return int(CURSOR_PATH.read_text().strip())
    return 0


def write_cursor(line_num: int) -> None:
    """Guarda la última línea procesada."""
    CURSOR_PATH.write_text(str(line_num))


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpieza de artículos scrapeados")
    parser.add_argument(
        "--force", action="store_true", help="Re-limpiar todo desde cero",
    )
    parser.add_argument(
        "--no-filter", action="store_true",
        help="No filtrar por sección (mantener deportes, entretenimiento, etc.)",
    )
    args = parser.parse_args()

    if not INPUT_PATH.exists():
        logger.error("No existe %s. Corre el scraper primero.", INPUT_PATH)
        return

    cursor = 0 if args.force else read_cursor()
    mode = "w" if args.force else "a"

    # Contar total de líneas para progreso
    with open(INPUT_PATH, encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)

    pending = total_lines - cursor
    if pending <= 0:
        logger.info("Todo limpio. %d artículos procesados, 0 pendientes.", cursor)
        return

    logger.info("Artículos en raw: %d | Ya limpiados: %d | Pendientes: %d",
                total_lines, cursor, pending)
    if not args.no_filter:
        logger.info("Filtro de secciones activo (se descartan deportes, entretenimiento, etc.)")

    cleaned_count = 0
    filtered_noise = 0
    discarded_short = 0

    with open(INPUT_PATH, encoding="utf-8") as fin, \
         open(OUTPUT_PATH, mode, encoding="utf-8") as fout:

        for i, line in enumerate(fin):
            if i < cursor:
                continue

            article = json.loads(line)

            # Filtrar secciones no políticas
            if not args.no_filter and _is_noise_section(article["url"]):
                filtered_noise += 1
                continue

            # Limpiar texto
            article["text"] = clean_article_text(
                article["text"],
                authors=article.get("authors"),
            )

            # Descartar si el texto limpio es muy corto
            if len(article["text"]) < 300:
                discarded_short += 1
                continue

            fout.write(json.dumps(article, ensure_ascii=False) + "\n")
            fout.flush()
            cleaned_count += 1

            if cleaned_count % 100 == 0:
                logger.info("  Procesados: %d/%d", cleaned_count, pending)

        write_cursor(total_lines)

    logger.info("Limpieza completada:")
    logger.info("  Procesados: %d", cleaned_count + filtered_noise + discarded_short)
    logger.info("  Guardados: %d", cleaned_count)
    logger.info("  Filtrados (sección no política): %d", filtered_noise)
    logger.info("  Descartados (< 300 chars): %d", discarded_short)
    logger.info("  Cursor actualizado a: %d", total_lines)
    logger.info("  Salida: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
