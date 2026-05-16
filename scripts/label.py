"""Etiquetado de noticias con LLM-as-a-Judge (Gemini).

Requiere la variable de entorno GEMINI_API_KEY.

Uso:
    python scripts/label.py
    python scripts/label.py --max-articles 10     # prueba con 10 artículos
    python scripts/label.py --force                # re-etiquetar desde cero
    python scripts/label.py --model gemini-1.5-pro
"""

import argparse
import logging
import os

# Cargar variables de .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Etiquetado LLM-as-a-Judge (Gemini)")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        help="Límite de artículos a etiquetar (default: todos)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-etiquetar todo desde cero",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gemini-2.0-flash",
        help="Modelo de Gemini (default: gemini-2.0-flash)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Archivo de entrada (default: data/raw/news_clean.jsonl)",
    )
    args = parser.parse_args()

    # Verificar API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error(
            "Falta GEMINI_API_KEY. Obtén una gratis en https://aistudio.google.com\n"
            "  export GEMINI_API_KEY='tu-key-aquí'"
        )
        return

    try:
        from google import genai
    except ImportError:
        logger.error("Instala el SDK de Google GenAI: pip install google-genai")
        return

    from pathlib import Path
    from src.labeling.judge import label_news_file

    client = genai.Client(api_key=api_key)
    input_path = Path(args.input) if args.input else None

    print()
    print("=" * 60)
    print("  IdeoGraphCO — Etiquetado LLM-as-a-Judge")
    print(f"  Motor: Gemini ({args.model})")
    print(f"  Máx artículos: {args.max_articles or 'todos'}")
    print(f"  Modo: {'forzado (desde cero)' if args.force else 'incremental'}")
    print("=" * 60)
    print()

    output = label_news_file(
        llm_client=client,
        input_path=input_path,
        llm_model=args.model,
        force=args.force,
        max_articles=args.max_articles,
        rate_limit_delay=1.5,  # tier pagado permite 1000+ RPM
    )

    print()
    print(f"  Resultado: {output}")
    print()


if __name__ == "__main__":
    main()
