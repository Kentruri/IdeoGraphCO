"""Catálogo de fuentes de noticias colombianas categorizadas por tipo de medio.

La categorización garantiza balance en el dataset para las 8 dimensiones
ideológicas del modelo IdeoVect.
"""

# ---------------------------------------------------------------------------
# Fuentes categorizadas por tipo de medio y dimensión ideológica que potencian
# ---------------------------------------------------------------------------

SOURCES_CONFIG: dict[str, dict[str, str]] = {
    # --- Nacionales tradicionales (línea base ideológica) ---
    "nacional": {
        "eltiempo": "https://www.eltiempo.com",
        "elespectador": "https://www.elespectador.com",
        "semana": "https://www.semana.com",
        "elnuevosiglo": "https://www.elnuevosiglo.com.co",
        "portafolio": "https://www.portafolio.co",
        "bluradio": "https://www.bluradio.com",
        "rcnradio": "https://www.rcnradio.com",
        "caracol": "https://www.caracol.com.co",
    },
    # --- Independientes e investigativos (populismo, doctrinarismo, progresismo) ---
    "independiente": {
        "lasillavacia": "https://www.lasillavacia.com",
        "cambio": "https://cambiocolombia.com",
        "cuestionpublica": "https://cuestionpublica.com",
        "voragine": "https://voragine.co",
        "lanuevaprensa": "https://www.lanuevaprensa.com.co",
        "mutante": "https://www.mutante.org",
        "razonpublica": "https://razonpublica.com",
    },
    # --- Institucionales (institucionalismo puro) ---
    "institucional": {
        "presidencia": "https://www.presidencia.gov.co/prensa/noticias",
        "vicepresidencia": "https://www.vicepresidencia.gov.co/prensa/noticias",
        "funcionpublica": "https://www.funcionpublica.gov.co/todas-las-noticias",
        "senado": "https://www.senado.gov.co/index.php/noticias",
    },
    # --- Regionales (personalismo local, soberanismo) ---
    "regional": {
        "elcolombiano": "https://www.elcolombiano.com",
        "elheraldo": "https://www.elheraldo.co",
        "eluniversal": "https://www.eluniversal.com.co",
        "vanguardia": "https://www.vanguardia.com",
        "laopinion": "https://www.laopinion.com.co",
        "elpaiscali": "https://www.elpais.com.co",
    },
    # --- Gremiales y especializadas (soberanismo vs. globalismo) ---
    "gremial": {
        "fecode": "https://fecode.edu.co",
        "andi": "https://www.andi.com.co",
    },
}

# ---------------------------------------------------------------------------
# Feeds RSS conocidos (más limpios que build() para noticias políticas)
# ---------------------------------------------------------------------------

RSS_FEEDS: dict[str, list[str]] = {
    "eltiempo": [
        "https://www.eltiempo.com/rss/colombia.xml",
        "https://www.eltiempo.com/rss/politica.xml",
    ],
    "elespectador": [
        "https://www.elespectador.com/rss/politica/feed/",
        "https://www.elespectador.com/rss/colombia/feed/",
    ],
    "semana": [
        "https://www.semana.com/rss/politica.xml",
    ],
}

# ---------------------------------------------------------------------------
# Vistas derivadas (se construyen automáticamente del catálogo)
# ---------------------------------------------------------------------------

# Vista plana: nombre → url
ALL_SOURCES: dict[str, str] = {}
for _sources in SOURCES_CONFIG.values():
    ALL_SOURCES.update(_sources)

# Mapeo inverso: nombre → categoría
SOURCE_CATEGORY: dict[str, str] = {}
for _cat, _sources in SOURCES_CONFIG.items():
    for _name in _sources:
        SOURCE_CATEGORY[_name] = _cat

CATEGORIES = list(SOURCES_CONFIG.keys())
