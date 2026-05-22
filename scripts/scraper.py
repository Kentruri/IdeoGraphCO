"""Pipeline completo del scraper: scrape → clean → filter en un solo comando.

Cada artículo pasa por las 3 etapas antes de guardarse. Solo los que el LLM
clasifica como "political_article" terminan en el archivo de salida final.

Uso:
    python scripts/scraper.py
    python scripts/scraper.py --max-articles 100
    python scripts/scraper.py --sources eltiempo lasillavacia
    python scripts/scraper.py --categories nacional independiente
    python scripts/scraper.py --no-filter           # solo scrape + clean, sin gastar API
    python scripts/scraper.py --model gemini-2.5-flash --rate-limit 2.5
"""

import argparse
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.core.paths import LOGS_DIR, RAW_DIR
from src.scraper.db import get_scraped_count
from src.scraper.pipeline import scrape_pipeline
from src.scraper.sources import CATEGORIES, SOURCES, SOURCES_BY_CATEGORY

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Silenciar logs ruidosos del SDK
for noisy in ("google_genai", "google_genai.types", "httpx", "httpcore"):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def resolve_source_names(
    categories: list[str] | None, sources: list[str] | None,
) -> list[str]:
    """Decide qué fuentes scrapear según los args."""
    if sources:
        return sources
    if categories:
        names: list[str] = []
        for cat in categories:
            if cat in SOURCES_BY_CATEGORY:
                names.extend(SOURCES_BY_CATEGORY[cat])
            else:
                logger.warning("Categoría '%s' no reconocida.", cat)
        return names
    return list(SOURCES.keys())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline completo: scrape → clean (regex) → filter (LLM)"
    )
    parser.add_argument(
        "--categories", nargs="+", choices=CATEGORIES, default=None,
        help="Categorías a scrapear (default: todas)",
    )
    parser.add_argument(
        "--sources", nargs="+", default=None,
        help="Fuentes individuales (ej: eltiempo lasillavacia)",
    )
    parser.add_argument(
        "--max-articles", type=int, default=50,
        help="Máximo de artículos POR FUENTE (default: 50)",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="JSONL de salida (default: data/raw/articles.jsonl)",
    )
    parser.add_argument(
        "--no-filter", action="store_true",
        help="No usar filter LLM (solo scrape + clean). Útil para iteraciones rápidas.",
    )
    parser.add_argument(
        "--model", type=str, default="gemini-2.5-flash-lite",
        help="Modelo Gemini para el filter (default: gemini-2.5-flash-lite)",
    )
    parser.add_argument(
        "--min-chars", type=int, default=800,
        help="Longitud mínima del artículo después del cleaning (default: 800)",
    )
    parser.add_argument(
        "--rate-limit", type=float, default=4.5,
        help="Segundos entre llamadas al filter LLM (default: 4.5)",
    )
    parser.add_argument(
        "--escalate-model", type=str, default="gemini-2.5-flash",
        help="Modelo al que escalar cuando el primario duda "
             "(default: gemini-2.5-flash, ~4x más caro). "
             "Usa --no-escalate para desactivar.",
    )
    parser.add_argument(
        "--escalate-threshold", type=float, default=0.7,
        help="Si confidence < este valor, se escala al modelo más caro (default: 0.7)",
    )
    parser.add_argument(
        "--no-escalate", action="store_true",
        help="Desactiva el escalado automático (siempre usa el modelo primario).",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Verbosidad de logs en stdout (default: INFO)",
    )
    parser.add_argument(
        "--filter-log", type=str, default=None,
        help="JSONL con cada decisión del filter LLM "
             "(default: logs/filter_decisions.jsonl). "
             "Útil para analizar distribución de confidence y calibrar.",
    )
    parser.add_argument(
        "--no-filter-log", action="store_true",
        help="Desactiva el log estructurado de decisiones del filter.",
    )
    args = parser.parse_args()

    # Configurar nivel de logs según --log-level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    output_path = (
        RAW_DIR / (args.output or "articles.jsonl")
        if args.output is None or "/" not in args.output
        else args.output
    )

    # Filter log estructurado (JSONL con keep/drop + confidence + reason)
    if args.no_filter_log:
        filter_log_path: Path | None = None
    else:
        filter_log_path = (
            Path(args.filter_log) if args.filter_log
            else LOGS_DIR / "filter_decisions.jsonl"
        )

    use_llm_filter = not args.no_filter
    llm_client = None

    if use_llm_filter:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error(
                "Falta GEMINI_API_KEY (configúralo en .env). "
                "Si no quieres usar el filter, pasa --no-filter.",
            )
            return
        try:
            from google import genai
        except ImportError:
            logger.error("Instala el SDK: pip install google-genai")
            return
        llm_client = genai.Client(api_key=api_key)

    selected_names = resolve_source_names(args.categories, args.sources)
    selected_sources = {n: SOURCES[n] for n in selected_names if n in SOURCES}

    if not selected_sources:
        logger.error("No hay fuentes válidas seleccionadas.")
        return

    logger.info(
        "BD histórica: %d artículos ya scrapeados previamente",
        get_scraped_count(),
    )

    escalate_model = None if args.no_escalate else args.escalate_model

    scrape_pipeline(
        sources=selected_sources,
        output_path=output_path,
        max_per_source=args.max_articles,
        use_llm_filter=use_llm_filter,
        llm_client=llm_client,
        llm_model=args.model,
        min_chars=args.min_chars,
        rate_limit_filter=args.rate_limit,
        filter_log_path=filter_log_path,
        escalate_model=escalate_model,
        escalate_threshold=args.escalate_threshold,
    )


if __name__ == "__main__":
    main()
