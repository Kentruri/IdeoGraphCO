"""Schema central del proyecto — fuente única de verdad para nombres y campos.

Estos constantes son compartidas por todos los módulos (scraper, agents,
training, inference) para evitar duplicación y desincronización.
"""

# Los 8 ejes ideológicos en orden canónico.
# Cualquier código que itere ejes DEBE usar esta lista.
AXIS_NAMES: list[str] = [
    "personalismo",
    "institucionalismo",
    "populismo",
    "doctrinarismo",
    "soberanismo",
    "globalismo",
    "conservadurismo",
    "progresismo",
]

# Campos canónicos del JSONL de un artículo (sin labels)
ARTICLE_FIELDS: tuple[str, ...] = (
    "id", "text", "title", "authors", "source", "category",
    "url", "date", "scraped_at",
)

# Campos canónicos del JSONL etiquetado (artículo + labels).
# El dataset es 100% político por construcción (filtrado aguas arriba),
# por eso no hay campo is_political.
LABELED_FIELDS: tuple[str, ...] = (
    "id", "text", "title", "source", "category", "url", "date",
    *AXIS_NAMES,
)
