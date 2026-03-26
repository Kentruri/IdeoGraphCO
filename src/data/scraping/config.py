"""Configuración de Newspaper4k para scraping de medios colombianos."""

from newspaper import Config


def get_newspaper_config() -> Config:
    """Configura Newspaper4k con User-Agent real para evitar bloqueos 403."""
    config = Config()
    config.browser_user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    config.request_timeout = 15
    config.language = "es"
    config.memoize_articles = True
    return config
