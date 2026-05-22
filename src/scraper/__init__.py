"""Scraper: scraping + cleaning + filter LLM en un solo módulo.

API pública:
- scrape_pipeline: orquestador del pipeline completo (recomendado)
- extract_article, scrape_source: building blocks (uso avanzado)
- is_real_article: filter LLM aislado
- clean_article_text: cleaner regex aislado
- get_scraped_count: contador del scraper_history.db
"""

from src.scraper.article_filter import is_real_article
from src.scraper.cleaner import clean_article_text
from src.scraper.db import get_scraped_count
from src.scraper.parser import extract_article, scrape_source
from src.scraper.pipeline import scrape_pipeline
from src.scraper.prompts import FILTER_SYSTEM_PROMPT

__all__ = [
    "FILTER_SYSTEM_PROMPT",
    "clean_article_text",
    "extract_article",
    "get_scraped_count",
    "is_real_article",
    "scrape_pipeline",
    "scrape_source",
]
