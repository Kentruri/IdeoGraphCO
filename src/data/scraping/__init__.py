from src.data.scraping.db import get_scraped_count
from src.data.scraping.parser import extract_article, scrape_source

__all__ = [
    "extract_article",
    "get_scraped_count",
    "scrape_source",
]
