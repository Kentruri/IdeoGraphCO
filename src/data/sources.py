"""Catálogo de fuentes de noticias colombianas para IdeoGraphCO.

Cada fuente define su estrategia de extracción:
- mode "sitemap": Descarga sitemap.xml y filtra URLs por sección política
- mode "direct": Todo el contenido es político, scrapear sin filtro

Flujo de prioridades por fuente:
1. Si tiene rss_feeds → RSS primero (más limpio y rápido)
2. Si mode="sitemap" → sitemap + url_filters
3. Si mode="direct" → sitemap sin filtro (para tener histórico)
4. Fallback → crawl de la página con trafilatura
"""

# Secciones de URL que indican contenido político/relevante
DEFAULT_POLITICAL_SECTIONS: list[str] = [
    "/politica/", "/nacion/", "/gobierno/", "/economia/",
    "/opinion/", "/judicial/", "/justicia/", "/congreso/",
    "/elecciones/", "/paz/", "/conflicto/", "/seguridad/",
    "/legislacion/", "/poder/", "/negocios/", "/empresas/",
]

# ---------------------------------------------------------------------------
# Catálogo de fuentes — formato por fuente
# ---------------------------------------------------------------------------

SOURCES: dict[str, dict] = {
    # ===========================
    # NACIONALES (línea base ideológica)
    # ===========================
    "eltiempo": {
        "url": "https://www.eltiempo.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/nacion/", "/justicia/", "/gobierno/"],
        "rss_feeds": [
            "https://www.eltiempo.com/rss/politica.xml",
            "https://www.eltiempo.com/rss/colombia.xml",
        ],
    },
    "elespectador": {
        "url": "https://www.elespectador.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/colombia/", "/judicial/", "/opinion/"],
        "rss_feeds": [],
    },
    "semana": {
        "url": "https://www.semana.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/nacion/", "/politica/", "/economia/", "/opinion/"],
        "rss_feeds": [],
    },
    "elnuevosiglo": {
        "url": "https://www.elnuevosiglo.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/opinion/", "/nacion/"],
        "rss_feeds": [],
    },
    "portafolio": {
        "url": "https://www.portafolio.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/economia/", "/negocios/", "/empresas/", "/opinion/"],
        "rss_feeds": [],
    },
    "bluradio": {
        "url": "https://www.bluradio.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/nacion/", "/economia/", "/judicial/"],
        "rss_feeds": [],
    },
    "rcnradio": {
        "url": "https://www.rcnradio.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/nacion/", "/economia/", "/judicial/"],
        "rss_feeds": [],
    },
    "caracol": {
        "url": "https://www.caracol.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/judicial/"],
        "rss_feeds": [],
    },

    # ===========================
    # INDEPENDIENTES (populismo, doctrinarismo, progresismo)
    # ===========================
    "lasillavacia": {
        "url": "https://www.lasillavacia.com",
        "category": "independiente",
        "mode": "direct",  # 100% político
        "url_filters": [],
        "rss_feeds": [
            "https://www.lasillavacia.com/feed/",
        ],
    },
    "cambio": {
        "url": "https://cambiocolombia.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "cuestionpublica": {
        "url": "https://cuestionpublica.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "voragine": {
        "url": "https://voragine.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://voragine.co/feed/",
        ],
    },
    "lanuevaprensa": {
        "url": "https://www.lanuevaprensa.com.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "mutante": {
        "url": "https://www.mutante.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.mutante.org/feed/",
        ],
    },
    "razonpublica": {
        "url": "https://razonpublica.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://razonpublica.com/feed/",
        ],
    },
    "volcanicas": {
        "url": "https://volcanicas.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://volcanicas.com/feed/",
        ],
    },
    "manifiesta": {
        "url": "https://manifiesta.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "las2orillas": {
        "url": "https://www.las2orillas.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.las2orillas.co/feed/",
        ],
    },
    "pulzo": {
        "url": "https://www.pulzo.com",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/nacion/", "/economia/"],
        "rss_feeds": [
            "https://www.pulzo.com/rss",
        ],
    },

    # ===========================
    # OPINIÓN / ANÁLISIS (refuerzan doctrinarismo y análisis político)
    # ===========================
    "dejusticia": {
        "url": "https://www.dejusticia.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.dejusticia.org/feed/",
        ],
    },
    "pares": {
        "url": "https://www.pares.com.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.pares.com.co/feed/",
        ],
    },
    "latinoamerica21": {
        "url": "https://latinoamerica21.com",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/colombia/", "/politica/", "/opinion/"],
        "rss_feeds": [
            "https://latinoamerica21.com/feed/",
        ],
    },

    # ===========================
    # INSTITUCIONALES (institucionalismo puro)
    # ===========================
    "presidencia": {
        "url": "https://www.presidencia.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "vicepresidencia": {
        "url": "https://www.vicepresidencia.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "funcionpublica": {
        "url": "https://www.funcionpublica.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "senado": {
        "url": "https://www.senado.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "camara": {
        "url": "https://www.camara.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.camara.gov.co/feed",
        ],
    },
    "contraloria": {
        "url": "https://www.contraloria.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "mininterior": {
        "url": "https://www.mininterior.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://www.mininterior.gov.co/feed/",
        ],
    },
    "cancilleria": {
        "url": "https://www.cancilleria.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "corteconstitucional": {
        "url": "https://www.corteconstitucional.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },

    # ===========================
    # REGIONALES (personalismo local, soberanismo)
    # ===========================
    "elcolombiano": {
        "url": "https://www.elcolombiano.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/colombia/", "/politica/", "/negocios/", "/opinion/"],
        "rss_feeds": [
            "https://www.elcolombiano.com/rss/colombia.xml",
        ],
    },
    "elheraldo": {
        "url": "https://www.elheraldo.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/judicial/", "/opinion/", "/colombia/"],
        "rss_feeds": [],
    },
    "eluniversal": {
        "url": "https://www.eluniversal.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/colombia/", "/opinion/"],
        "rss_feeds": [],
    },
    "vanguardia": {
        "url": "https://www.vanguardia.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/opinion/", "/area-metropolitana/"],
        "rss_feeds": [],
    },
    "laopinion": {
        "url": "https://www.laopinion.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/judicial/", "/opinion/"],
        "rss_feeds": [],
    },
    "elpaiscali": {
        "url": "https://www.elpais.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/judicial/", "/opinion/", "/cali/"],
        "rss_feeds": [],
    },

    # ===========================
    # GREMIALES (soberanismo vs. globalismo)
    # ===========================
    "fecode": {
        "url": "https://fecode.edu.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [
            "https://fecode.edu.co/feed/",
        ],
    },
    "andi": {
        "url": "https://www.andi.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "valorescristianos": {
        "url": "http://periodicovalorescristianos.com",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
}

# ---------------------------------------------------------------------------
# Vistas derivadas
# ---------------------------------------------------------------------------

CATEGORIES: list[str] = list({s["category"] for s in SOURCES.values()})

# Fuentes agrupadas por categoría
SOURCES_BY_CATEGORY: dict[str, list[str]] = {}
for _name, _conf in SOURCES.items():
    cat = _conf["category"]
    SOURCES_BY_CATEGORY.setdefault(cat, []).append(_name)
