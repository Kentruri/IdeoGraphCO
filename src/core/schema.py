"""Schema central del proyecto — fuente única de verdad para nombres y campos.

Estos constantes son compartidas por todos los módulos (scraper, agents,
training, inference) para evitar duplicación y desincronización.

Design note: el proyecto es un CLASIFICADOR MULTICLASE SINGLE-LABEL con
8 clases mutuamente excluyentes (una ideología dominante por artículo). Las
"opuestas" (populismo ↔ institucionalismo, etc.) son clases distintas,
no dos ejes de un mismo espacio bidimensional.
"""

# Las 8 clases ideológicas en orden canónico.
# Definen la salida del clasificador (Softmax 8-way).
# El índice de cada clase en esta lista es su ID entero.
IDEOLOGY_CLASSES: list[str] = [
    "personalismo",
    "institucionalismo",
    "populismo",
    "doctrinarismo",
    "soberanismo",
    "globalismo",
    "conservadurismo",
    "progresismo",
]

# Número de clases (fuente única).
NUM_CLASSES: int = len(IDEOLOGY_CLASSES)

# Mapeos convenientes clase → índice e índice → clase.
CLASS_TO_IDX: dict[str, int] = {name: i for i, name in enumerate(IDEOLOGY_CLASSES)}
IDX_TO_CLASS: dict[int, str] = {i: name for i, name in enumerate(IDEOLOGY_CLASSES)}

# Pares opuestos (para análisis de errores en OE3), según los 4 ejes teóricos
# del anteproyecto (§5.3, alineados con V-Party/V-Dem):
#   - Gobernanza y discurso estamental: populismo (retórica anti-élite) frente
#     al compromiso con el pluralismo institucional.
#   - Estructura de liderazgo: personalismo (control individual del líder)
#     frente al partido guiado por doctrina.
# Un error entre opuestos es más grave que uno entre clases ortogonales.
OPPOSITE_PAIRS: list[tuple[str, str]] = [
    ("populismo", "institucionalismo"),
    ("personalismo", "doctrinarismo"),
    ("soberanismo", "globalismo"),
    ("conservadurismo", "progresismo"),
]

# Campos canónicos del JSONL de un artículo (sin labels).
# `authors` NO se persiste: solo se usa DURANTE el scraping para borrar las
# líneas de firma del cuerpo (parser.clean_article_text). Guardarlo después
# es peso muerto, y un nombre de autor repetido sería otra huella de fuente
# que el clasificador podría usar como atajo.
ARTICLE_FIELDS: tuple[str, ...] = (
    "id", "text", "title", "source", "category", "url", "date", "scraped_at",
)

# Campos canónicos del JSONL etiquetado (artículo + label categórico).
# Formato NUEVO (post-refactor a clasificador):
#     {"id": ..., "text": ..., ..., "label": "populismo", "label_idx": 2}
# Formato LEGACY (silver_set.jsonl actual, escala continua):
#     {"id": ..., "text": ..., ..., "personalismo": 0.42, "populismo": 0.83, ...}
# El Dataset soporta ambos formatos y convierte legacy con argmax al vuelo
# hasta que se decida re-etiquetar (ver docs/preguntas-director.md tema 5).
LABELED_FIELDS: tuple[str, ...] = (
    "id", "text", "title", "source", "category", "url", "date",
    "label", "label_idx",
)
