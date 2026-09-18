"""Etiquetado de noticias con LLM-as-a-Judge (Gemini).

Requiere la variable de entorno GEMINI_API_KEY.

Uso:
    python scripts/label.py
    python scripts/label.py --max-articles 10     # prueba con 10 artículos
    python scripts/label.py --force                # re-etiquetar desde cero
    python scripts/label.py --model gemini-1.5-pro
"""

import argparse
import json
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
        default="gemini-2.5-flash",
        help="Modelo de Gemini (default: gemini-2.5-flash)",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Archivo de entrada (default: data/raw/articles.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Archivo de salida (default: data/silver/silver_set.jsonl)",
    )
    parser.add_argument(
        "--gold-ids",
        type=str,
        default=None,
        help="JSON con los IDs del gold, que NO deben recibir etiqueta silver "
             "(default: annotation/gold_set_v2_ids.json)",
    )
    parser.add_argument(
        "--allow-gold-in-silver",
        action="store_true",
        help="Etiquetar también el gold. Solo para pruebas: contamina el "
             "conjunto de prueba y vuelve circulares las métricas del OE3",
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
    from src.agents.silver.judge import label_news_file

    client = genai.Client(api_key=api_key)
    input_path = Path(args.input) if args.input else None
    output_path = Path(args.output) if args.output else None

    # El gold es el conjunto de PRUEBA: si el juez le pone etiqueta silver, el
    # modelo se acaba evaluando contra otro modelo en vez de contra el humano.
    exclude_ids: set[str] = set()
    if not args.allow_gold_in_silver:
        from src.core.paths import ROOT as _ROOT
        gold_path = Path(args.gold_ids) if args.gold_ids else \
            _ROOT / "annotation" / "gold_set_v2_ids.json"
        if gold_path.exists():
            with open(gold_path, encoding="utf-8") as f:
                data = json.load(f)
            exclude_ids = set(data if isinstance(data, list) else data.get("ids", []))
        else:
            logger.warning(
                "No encontré %s: NINGÚN artículo quedará fuera del silver. "
                "Si ya muestreaste el gold, esto contaminaría el test.",
                gold_path,
            )

    print()
    print("=" * 60)
    print("  IdeoGraphCO — Etiquetado LLM-as-a-Judge")
    print(f"  Motor: Gemini ({args.model})")
    print(f"  Máx artículos: {args.max_articles or 'todos'}")
    print(f"  Modo: {'forzado (desde cero)' if args.force else 'incremental'}")
    print(f"  Gold excluido: {len(exclude_ids):,} artículos"
          if exclude_ids else "  Gold excluido: NINGUNO ⚠")
    print("=" * 60)
    print()

    output = label_news_file(
        llm_client=client,
        input_path=input_path,
        output_path=output_path,
        llm_model=args.model,
        force=args.force,
        max_articles=args.max_articles,
        rate_limit_delay=4.5,  # tier pagado permite 1000+ RPM
        exclude_ids=exclude_ids,
    )

    print()
    print(f"  Resultado: {output}")
    print()


if __name__ == "__main__":
    main()
