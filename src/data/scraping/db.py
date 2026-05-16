"""Deduplicación persistente de artículos con SQLite.

Mantiene un registro de URLs y hashes de contenido ya descargados
para evitar re-descargas entre ejecuciones del scraper.
Deduplica por URL y por contenido (misma noticia republicada con URL diferente).
"""

import hashlib
import sqlite3
from pathlib import Path

from src.paths import DATA_DIR

DB_PATH = DATA_DIR / "scraper_history.db"


def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Crea o abre la base de datos y asegura que la tabla exista."""
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS scraped_urls (
            url TEXT PRIMARY KEY,
            content_hash TEXT,
            source TEXT NOT NULL,
            category TEXT NOT NULL,
            scraped_at TEXT NOT NULL
        )
        """
    )
    # Índice para búsquedas rápidas por hash de contenido
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_hash ON scraped_urls(content_hash)"
    )
    conn.commit()
    return conn


def compute_content_hash(text: str) -> str:
    """Genera un hash MD5 del texto para detectar contenido duplicado."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_already_scraped(url: str, db_path: Path = DB_PATH) -> bool:
    """Verifica si una URL ya fue descargada previamente."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute("SELECT 1 FROM scraped_urls WHERE url = ?", (url,)).fetchone()
        return row is not None
    finally:
        conn.close()


def is_duplicate_content(content_hash: str, db_path: Path = DB_PATH) -> bool:
    """Verifica si ya existe un artículo con el mismo contenido (distinta URL)."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT 1 FROM scraped_urls WHERE content_hash = ?", (content_hash,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def mark_as_scraped(
    url: str,
    content_hash: str,
    source: str,
    category: str,
    scraped_at: str,
    db_path: Path = DB_PATH,
) -> None:
    """Registra una URL y su hash de contenido como descargados."""
    conn = _get_connection(db_path)
    try:
        conn.execute(
            "INSERT OR IGNORE INTO scraped_urls (url, content_hash, source, category, scraped_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (url, content_hash, source, category, scraped_at),
        )
        conn.commit()
    finally:
        conn.close()


def get_scraped_count(db_path: Path = DB_PATH) -> int:
    """Devuelve el número total de URLs registradas."""
    conn = _get_connection(db_path)
    try:
        row = conn.execute("SELECT COUNT(*) FROM scraped_urls").fetchone()
        return row[0] if row else 0
    finally:
        conn.close()
