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

# NOTA DE ALCANCE: el corpus es SOLO de prensa colombiana. En una auditoria
# (ago-2026) se dieron de baja 19 fuentes internacionales que estaban
# registradas por "cubrir Colombia" pero cuya cobertura medida era mayormente
# de otros paises: BBC Mundo (12% Colombia), DW (0%), France 24 (4%), RFI (7%),
# RT (0%), Sputnik (16%), El Pais America (13%), NTN24 (30%), InSight Crime
# (13%), HRW (31%), CIDH (14%), FESCOL (40%), Boll (30%), Forbes Colombia (55%,
# con traducciones de Forbes US), y las regionales Latinoamerica21, CELAG,
# Nueva Sociedad, Diario Las Americas y CLIP.
#
# El motivo no es solo de alcance: el texto extranjero introduce otra variedad
# de espanol y el vocabulario de otro sistema politico, que el clasificador
# puede aprender como ATAJO para predecir la clase ideologica en vez de
# aprender ideologia. Antes de anadir un medio extranjero, medir que porcentaje
# de su contenido es colombiano con scripts/verify_sources.py.

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
        "news_sitemaps": [
            "https://www.elespectador.com/arc/outboundfeeds/news-sitemap/?outputType=xml",
        ],
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
        "news_sitemaps": [
            "https://www.bluradio.com/content-sitemap-latest.xml",
        ],
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
        "category": "judicial",
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

    # =======================================================================
    # AMPLIACIÓN — fuentes adicionales para refuerzo de diversidad ideológica
    # =======================================================================

    # --- Nacionales y económicos ---
    "larepublica": {
        "url": "https://www.larepublica.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": [
            "/economia/", "/inside/", "/finanzas/",
            "/empresas/", "/analisis/", "/caja-fuerte/",
        ],
        "rss_feeds": [],  # usa sitemaps mensuales (gzip) como fuente prioritaria
    },
    "valoraanalitik": {
        "url": "https://www.valoraanalitik.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": [
            "/economia/", "/energia/", "/infraestructura/",
            "/mercados/", "/politica/",
        ],
        "rss_feeds": ["https://www.valoraanalitik.com/feed/"],
    },
    "dataifx": {
        "url": "https://www.dataifx.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": [
            "/noticias/", "/macroeconomia/", "/dolar/",
            "/mercados-y-finanzas/",
        ],
        "rss_feeds": ["https://www.dataifx.com/rss.xml"],
    },
    "infobae_colombia": {
        # Los filtros previos no servian: /colombia/noticias/politica/ y
        # /america/colombia/ no existen (las notas son /colombia/AAAA/MM/DD/slug)
        # y /economia/ enganchaba la seccion de ARGENTINA. El sitemap del dominio
        # enumera todos los paises, asi que hay que acotar por /colombia/ y entrar
        # por el news-sitemap de la seccion, que es fresco y ya viene acotado.
        "url": "https://www.infobae.com/colombia/",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/colombia/"],
        "rss_feeds": [],
        "news_sitemaps": [
            "https://www.infobae.com/arc/outboundfeeds/news-sitemap/category/colombia/",
        ],
    },
    "kienyke": {
        "url": "https://www.kienyke.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/kien-es-kien/", "/politica-y-poder/"],
        "rss_feeds": ["https://www.kienyke.com/feed"],
    },
    "publimetro_co": {
        "url": "https://www.publimetro.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/politica/", "/bogota/"],
        "rss_feeds": [],
    },

    # --- Independientes (territoriales, investigación, alternativos) ---
    "rutasdelconflicto": {
        "url": "https://rutasdelconflicto.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://rutasdelconflicto.com/feed/"],
    },
    "cerosetenta": {
        "url": "https://cerosetenta.uniandes.edu.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cerosetenta.uniandes.edu.co/feed/"],
    },
    "ligacontraelsilencio": {
        "url": "https://ligacontraelsilencio.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ligacontraelsilencio.org/feed/"],
    },
    "tercercanal": {
        "url": "https://tercercanal.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "pluralidadz": {
        "url": "https://pluralidadz.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://pluralidadz.com/feed/"],
    },
    "prensarural": {
        "url": "https://prensarural.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://prensarural.org/spip/spip.php?page=backend"],
    },

    # --- Opinión / think tanks (políticas públicas, balance ideológico) ---
    "fedesarrollo": {
        "url": "https://www.fedesarrollo.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "anif": {
        "url": "https://www.anif.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "icpcolombia": {
        "url": "https://www.icpcolombia.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "cinep": {
        "url": "https://www.cinep.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },

    # --- Regionales (dinámicas locales y poderes territoriales) ---
    "proclamadelcauca": {
        "url": "https://www.proclamadelcauca.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/noticias-cauca/", "/opinion/"],
        "rss_feeds": ["https://www.proclamadelcauca.com/feed/"],
    },
    "diariodelsur": {
        "url": "https://diariodelsur.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/nacional/", "/opinion/"],
        "rss_feeds": [],
    },
    "elpilon": {
        "url": "https://elpilon.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica-pilon/", "/opinion-pilon/", "/economia-pilon/"],
        "rss_feeds": ["https://elpilon.com.co/feed/"],
    },
    "lapatria": {
        "url": "https://www.lapatria.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/nacional/", "/opinion/"],
        "rss_feeds": [],
    },
    "boyacasietedias": {
        "url": "https://boyacasietedias.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/boyaca/", "/opinion/"],
        "rss_feeds": ["https://boyacasietedias.com.co/feed/"],
    },

    # --- Gremiales y sindicales (presión corporativa y sindicalismo) ---
    "asobancaria": {
        "url": "https://www.asobancaria.com",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "sac": {
        "url": "https://sac.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "fenalco": {
        "url": "https://www.fenalco.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "colfecar": {
        "url": "https://colfecar.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "cut": {
        "url": "https://cut.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cut.org.co/feed/"],
    },

    # --- Institucionales (regulación del Estado, datos oficiales) ---
    "banrep": {
        "url": "https://www.banrep.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "dane": {
        "url": "https://www.dane.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "jep": {
        "url": "https://www.jep.gov.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "fiscalia": {
        "url": "https://www.fiscalia.gov.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "procuraduria": {
        "url": "https://www.procuraduria.gov.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },

    # =======================================================================
    # AMPLIACIÓN 2 — Internacional, judicial, regionales étnicos, think tanks
    # =======================================================================

    # --- Internacional con foco en Colombia ---

    # --- Judicial / técnico-legal (nueva categoría) ---
    "ambitojuridico": {
        "url": "https://www.ambitojuridico.com",
        "category": "judicial",
        "mode": "sitemap",
        "url_filters": [
            "/nacional/", "/administrativo/", "/constitucional/",
            "/penal/", "/laboral/",
        ],
        "rss_feeds": ["https://www.ambitojuridico.com/rss"],
    },
    "legis": {
        # OJO: paywall fuerte en buena parte del sitio; el filter LLM va a
        # descartar mucho como "garbage" si solo agarra previews.
        "url": "https://www.legis.com.co",
        "category": "judicial",
        "mode": "sitemap",
        "url_filters": ["/legislacion/", "/jurisprudencia/", "/doctrina/"],
        "rss_feeds": [],
    },

    # --- Regionales territoriales (zonas críticas no cubiertas antes) ---
    "choco7dias": {
        "url": "https://choco7dias.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://choco7dias.com/feed/"],
    },
    "elmeridiano": {
        "url": "https://elmeridiano.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/judicial/", "/opinion/", "/cordoba/"],
        "rss_feeds": ["https://elmeridiano.co/feed/"],
    },
    "periodicodelmeta": {
        "url": "https://periodicodelmeta.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://periodicodelmeta.com/feed/"],
    },
    "diariodelhuila": {
        "url": "https://www.diariodelhuila.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/politica/", "/economia/", "/judicial/", "/opinion/",
        ],
        "rss_feeds": ["https://www.diariodelhuila.com/feed/"],
    },

    # --- Voces étnicas y territoriales (representación) ---
    "agendapropia": {
        "url": "https://agendapropia.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://agendapropia.co/feed/"],
    },
    "viveafro": {
        "url": "https://revista-viveafro.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://revista-viveafro.com/feed/"],
    },

    # --- Think tanks adicionales (agenda política y electoral) ---
    "fip": {
        "url": "https://www.ideaspaz.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "moe": {
        "url": "https://www.moe.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },

    # =======================================================================
    # AMPLIACIÓN 3 — barrido sistematico de 10 angulos (219 altas, 83 -> 302)
    #
    # Verificadas una por una con curl: dominio vivo tras redirects, feeds RSS
    # que responden 200 con XML valido (no adivinados), sitemap real, y HTML
    # crudo con el cuerpo del articulo. 36 candidatos mas quedaron descartados
    # por WAF (Cloudflare/Imperva), contenido solo en PDF o servidor caido.
    #
    # Cierra tres huecos del corpus previo:
    #   - Geografico: Arauca, Casanare, Putumayo, Caqueta, Guaviare, Vichada,
    #     Guainia, San Andres, Tolima, Quindio, Risaralda, Sucre, La Guajira,
    #     Magdalena Medio, Buenaventura y Soacha estaban en cero.
    #   - Ideologico: conservadurismo (religioso, agro-gremial, militar y
    #     prensa regional tradicional) y soberanismo (petroleo, frontera,
    #     indigena, maritimo) tenian una sola fuente o ninguna.
    #   - De actor: ministerios, agencias, altas cortes y partidos politicos
    #     no estaban representados.
    #
    # OJO al entrenar: la izquierda doctrinaria trae mucho mas volumen que la
    # derecha (desdeabajo ~24k articulos vs. partidoconservador 148), y las 64
    # fuentes institucionales comparten el registro del comunicado oficial.
    # Hacen falta cupos por fuente antes del judge, no despues.
    # =======================================================================

    # =======================================================================
    # AMPLIACIÓN 2 — cobertura territorial completa + balance ideológico
    # (219 fuentes verificadas con curl: vivas, políticas y scrapeables)
    # =======================================================================

    # --- Regionales: Orinoquía (Arauca, Casanare, Meta) ---
    "lavozdelcinaruco": {
        "url": "https://lavozdelcinaruco.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://lavozdelcinaruco.com/feed/"],
    },
    "alairenoticias": {
        "url": "https://alairenoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/arauca/", "/politica/", "/noticias-politicas-colombia/",
            "/orden-publico/", "/conflicto-armado/", "/frontera/",
            "/seguridad/", "/regiones/", "/saravena/", "/tame/",
            "/arauquita/", "/puerto-rondon/",
        ],
        "rss_feeds": ["https://alairenoticias.com/feed/"],  # OJO: CDN Hostinger devuelve 403 con reto JS si el ritmo es alto
    },
    "meridiano70": {
        "url": "https://meridiano70.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://meridiano70.co/feed/"],
    },
    "elcuartomosquetero": {
        "url": "https://elcuartomosquetero.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://elcuartomosquetero.com/feed/"],  # OJO: servidor lento e intermitente, subir timeout a >=60s
    },
    "diariodecasanare": {
        "url": "https://www.diariodecasanare.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.diariodecasanare.com/feed/"],
    },
    "prensalibrecasanare": {
        "url": "https://prensalibrecasanare.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/yopal/", "/casanare/", "/judicial/", "/opinion/", "/salud/"],
        "rss_feeds": ["https://prensalibrecasanare.com/rss.xml"],  # OJO: mojibake en títulos/slugs y baja densidad política por pieza
    },
    "eldiariodelllano": {
        "url": "https://eldiariodelllano.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://eldiariodelllano.com/feed/"],
    },
    "casanarenoticias": {
        "url": "https://www.casanarenoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/index.php/component/k2/item/", "/index.php/politica/",
            "/index.php/regional/", "/index.php/nacional/", "/index.php/judicial/",
        ],
        "rss_feeds": [  # OJO: sin sitemap; el feed raíz es inútil, solo sirven los de sección
            "https://www.casanarenoticias.com/index.php/politica?format=feed&type=rss",
            "https://www.casanarenoticias.com/index.php/regional?format=feed&type=rss",
            "https://www.casanarenoticias.com/index.php/nacional?format=feed&type=rss",
        ],
    },
    "quepasayopal": {
        "url": "https://quepasayopal.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://quepasayopal.com/feed/"],  # OJO: volumen medio, cadencia no diaria
    },
    "villavicenciodiaadia": {
        "url": "https://www.villavicenciodiaadia.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS (los /feed sirven la portada en HTML)
    },

    # --- Regionales: Amazonía y sur (Putumayo, Caquetá, Guaviare, Vichada/Guainía) ---
    "miputumayo": {
        "url": "https://miputumayo.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://miputumayo.com.co/feed/"],
    },
    "conexionputumayo": {
        "url": "https://conexionputumayo.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://conexionputumayo.com/feed/"],  # OJO: bajo volumen y contenido afiliado/SEO no periodístico en portada
    },
    "lanoticiaputumayo": {
        "url": "https://lanoticiaputumayo.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://lanoticiaputumayo.com/feed/"],
    },
    "lenteregional": {
        "url": "https://lenteregional.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://lenteregional.com/feed/"],  # OJO: sitemap con 5 URLs de páginas (inservible), el descubrimiento real es el RSS
    },
    "lanacion_neiva": {
        "url": "https://www.lanacion.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.lanacion.com.co/feed/"],  # OJO: club de suscriptores visible pero el cuerpo se entrega completo
    },
    "marandua": {
        "url": "https://marandua.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://marandua.com.co/feed/"],
    },
    "guaviareestereo": {
        "url": "https://guaviareestereo.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://guaviareestereo.com/feed/"],  # OJO: spam de casino inyectado en el archivo y secciones de audio sin texto
    },
    "elmorichal": {
        "url": "https://elmorichal.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://elmorichal.com/feed/"],  # OJO: volumen bajo por diseño (periodismo lento)
    },

    # --- Regionales: Caribe (La Guajira, Magdalena, Sucre, Atlántico, Bolívar, Córdoba, San Andrés) ---
    "diariodelnorte": {
        "url": "https://diariodelnorte.net",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/laguajira/", "/judiciales/", "/nacion/", "/caribe/",
            "/opinion/", "/editorial/", "/uncategorised/",
        ],
        "rss_feeds": ["https://diariodelnorte.net/feed/"],
    },
    "laguajirahoy": {
        "url": "https://laguajirahoy.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/politica/", "/judiciales/", "/judiciales-2/", "/la-guajira/",
            "/riohacha/", "/riohacha-4/", "/exclusivo/", "/comunidad/",
            "/comunidad-3/", "/medio-ambiente/", "/cultura/",
        ],
        "rss_feeds": [  # OJO: bloquea clientes sin UA de navegador; los <loc> del sitemap vienen en CDATA
            "https://laguajirahoy.com/rss.xml",
            "https://laguajirahoy.com/feed/",
        ],
    },
    "guajiranews": {
        "url": "https://guajiranews.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/destacadas/", "/actualidad/", "/actualidad-politica/", "/politica/",
            "/judiciales/", "/opinion/", "/cronica/", "/especial/",
        ],
        "rss_feeds": ["https://guajiranews.com/feed/"],  # OJO: CDN Hostinger con reto JS si el ritmo es alto
    },
    "laguajiranoticias": {
        "url": "https://www.laguajiranoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.laguajiranoticias.com/feed/"],
    },
    "diariolaguajira": {
        "url": "https://diariolaguajira.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/es/"],
        "rss_feeds": ["https://diariolaguajira.com.co/feed/posts"],  # OJO: sitio multilingüe (/en/) y sufijos '-1' duplicados
    },
    "seguimiento": {
        "url": "https://seguimiento.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/la-samaria/", "/magdalena/", "/la-region-caribe/", "/colombia/",
            "/opinan-los-expertos/", "/opinan-los-samarios/", "/la-hamaca/",
            "/para-no-olvidar/",
        ],
        "rss_feeds": ["https://seguimiento.co/rss.xml"],
    },
    "hoydiariomagdalena": {
        "url": "https://hoydiariodelmagdalena.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/archivos/"],
        "rss_feeds": [],  # OJO: sin RSS ni sitemap (Next.js con SSR) -> depende del crawl de /categoria/*
    },
    "elinformador": {
        "url": "https://www.elinformador.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/index.php/el-magdalena", "/index.php/la-ciudad", "/index.php/judiciales",
            "/index.php/opinion", "/index.php/columnistas", "/index.php/region-caribe",
            "/index.php/general",
        ],
        "rss_feeds": [  # OJO: sin sitemap y los feeds Joomla van 2-3 semanas rezagados
            "https://www.elinformador.com.co/index.php?format=feed&type=rss",
            "https://www.elinformador.com.co/index.php/el-magdalena?format=feed&type=rss",
        ],
    },
    "sucrenoticias": {
        "url": "https://sucrenoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://sucrenoticias.com/feed/"],  # OJO: sin publicar desde jul-2026, sirve para backfill histórico
    },
    "zonacero": {
        "url": "https://zonacero.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/judiciales/", "/opinion/", "/generales/"],
        "rss_feeds": [],  # OJO: sitemap roto (loc apuntan a http://default/) y el rss.xml solo trae 3 items (2 basura) -> dejar que caiga al crawl
    },
    "bolivarense": {
        "url": "https://bolivarense.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://bolivarense.com/feed/"],
    },
    "larazoncordoba": {
        "url": "https://larazon.co",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://larazon.co/feed/"],  # OJO: caché frío, primera petición puede tardar >25s (timeout >=30s)
    },
    "archipielagopress": {
        "url": "https://www.thearchipielagopress.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.thearchipielagopress.co/feed/"],  # OJO: publica algo en inglés/creole, requiere detección de idioma
    },
    "sanandreshoy": {
        "url": "https://sanandreshoy.net",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/actualidad/", "/nacionales/", "/opinion-y-politica/",
            "/economia/", "/internacionales/", "/salud/",
        ],
        "rss_feeds": ["https://sanandreshoy.net/feed/"],  # OJO: el sitemap_index miente en lastmod, leer los post-sitemapN.xml
    },
    "diocesisdecucuta": {
        "url": "https://diocesisdecucuta.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://diocesisdecucuta.com/feed/"],  # OJO: ~80% devocional/litúrgico, tasa de descarte del filtro LLM muy alta
    },

    # --- Regionales: Bogotá y Cundinamarca ---
    "periodismopublico": {
        "url": "https://periodismopublico.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://periodismopublico.com/feed"],
    },
    "soachailustrada": {
        "url": "https://soachailustrada.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://soachailustrada.com/feed/"],
    },
    "extrategiamedios": {
        "url": "https://extrategiamedios.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://extrategiamedios.com/feed/"],  # OJO: publica notas SEO de apuestas que el filtro LLM debe descartar
    },

    # --- Regionales: Tolima, Eje Cafetero ---
    "elnuevodia": {
        "url": "https://www.elnuevodia.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/politica/", "/judicial/", "/economica/", "/opinion/",
            "/tolima/", "/ibague/", "/actualidad/", "/colombia/",
        ],
        "rss_feeds": ["https://www.elnuevodia.com.co/rss.xml"],
    },
    "elcronista": {
        "url": "https://elcronista.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/politica", "/economia", "/judicial", "/opinion",
            "/actualidad", "/destacadas", "/nacion", "/reportajes",
        ],
        "rss_feeds": [],  # OJO: sin RSS; el HTML trae restos del panel de administración ('| Editar', /iadmin/)
    },
    "cronicadelquindio": {
        "url": "https://cronicadelquindio.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/actualidad/", "/opinion/", "/judicial/", "/quindio/", "/armenia/"],
        "rss_feeds": [],  # OJO: sin RSS (soft-404) y paywall parcial en /noticias/suscriptores/
    },
    "elquindiano": {
        "url": "https://elquindiano.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS; el sitemap contiene artículos de prueba del CMS (test1, titulo1, articulo-pepe)
    },
    "eldiariopereira": {
        "url": "https://www.eldiario.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/noticias/politica/", "/noticias/economia/", "/noticias/risaralda/",
            "/noticias/colombia/", "/judicial/", "/opinion/", "/actualidad/", "/editorial/",
        ],
        "rss_feeds": ["https://www.eldiario.com.co/feed/"],
    },
    "eje21": {
        "url": "https://www.eje21.com.co",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.eje21.com.co/feed/"],
    },
    "lacoladerata": {
        "url": "https://www.lacoladerata.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/conlupa/", "/opinion/", "/ojoalacorrupcion/", "/areneros/"],
        "rss_feeds": ["https://www.lacoladerata.co/feed/"],  # OJO: /sitemap.xml es legacy de 2012, el válido es /wp-sitemap.xml; feed stale
    },

    # --- Regionales: Antioquia, Valle, Pacífico, Santander, Cauca, Nariño ---
    "minuto30": {
        "url": "https://www.minuto30.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.minuto30.com/feed/"],  # OJO: sitemap dominado por avisos de desaparecidos, deportes y farándula -> coste alto del filtro LLM
    },
    "radio360": {
        "url": "https://360radio.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://360radio.com.co/feed/"],
    },
    "diariooccidente": {
        "url": "https://occidente.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/politica/", "/cali/", "/regionales/", "/opinion/",
            "/empresario/", "/colombia/", "/area-legal/",
        ],
        "rss_feeds": ["https://occidente.co/feed/"],
    },
    "buenaventuraenlinea": {
        "url": "https://buenaventuraenlinea.com",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://buenaventuraenlinea.com/feed/"],  # OJO: el sitemap conserva posts demo del tema en inglés
    },
    "elfrente": {
        "url": "https://elfrente.com.co",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://elfrente.com.co/rss/"],  # OJO: Ghost inyecta bloques 'Resumen con IA' / 'Línea del tiempo · IA' -> el cleaner DEBE quitarlos
    },
    "riogrande": {
        "url": "https://www.riogrande.com.co",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.riogrande.com.co/feed/"],
    },
    "elliberalpopayan": {
        "url": "https://elliberalpopayan.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [
            "/mi-ciudad/", "/mi-region/", "/judicial/",
            "/opinion/", "/editorial/", "/nacional/",
        ],
        "rss_feeds": ["https://elliberalpopayan.com/feed/"],
    },
    "elcontraste": {
        "url": "https://elcontraste.co",
        "category": "regional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS y sin secciones en la URL -> toda la carga recae en el filtro LLM
    },

    # --- Nacionales (radio, señales internacionales con redacción propia, económicos) ---
    "lafm": {
        "url": "https://www.lafm.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/economia/", "/orden-publico/", "/actualidad/", "/sociedad/"],
        "rss_feeds": [],  # OJO: sin RSS; el sitemap se declara en /sitemapindex y /sitemapnews SIN extensión .xml
    },
    "bloomberglinea": {
        "url": "https://www.bloomberglinea.com/latinoamerica/colombia/",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/latinoamerica/colombia/"],
        "rss_feeds": ["https://www.bloomberglinea.com/arc/outboundfeeds/rss/latinoamerica/colombia.xml"],  # OJO: paywall declarado en el HTML (el cuerpo se extrajo completo, vigilar)
    },

    # --- Independientes: derecha / opositores al petrismo (déficit del corpus) ---
    "losirreverentes": {
        "url": "https://losirreverentes.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://losirreverentes.com/feed/"],
    },
    "elexpediente": {
        "url": "https://elexpediente.co",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://elexpediente.co/feed/"],
    },
    "laotracara": {
        "url": "https://laotracara.co",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [
            "/opinion/", "/destacados/", "/nota-ciudadania/",
            "/ecos-politicos/", "/actualidad/", "/recomendados/",
        ],
        "rss_feeds": [],  # OJO: sin RSS; excluir /general/ (resultados de lotería)
    },
    "confidencialnoticias": {
        "url": "https://confidencialnoticias.com",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [
            "/nacion/", "/politica/", "/opinion/", "/economia/", "/judicial/",
            "/bogota/", "/lo-mas-confidencial/", "/voces-confidencial/",
        ],
        "rss_feeds": ["https://confidencialnoticias.com/feed/"],  # OJO: requiere UA de navegador; el único sitemap XML válido es /sitemap_index.xml
    },
    "elcatolicismo": {
        "url": "https://www.elcatolicismo.com.co",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": ["/editorial/", "/opinion/", "/actualidad-y-analisis/"],
        "rss_feeds": [],  # OJO: /rss.xml es XML válido pero con 0 items; /iglesia-hoy/ queda fuera por ser puramente eclesial
    },

    # --- Independientes: izquierda, contrainformación y movimientos ---
    "colombiainforma": {
        "url": "https://www.colombiainforma.info",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.colombiainforma.info/feed/"],
    },
    "semanariovoz": {
        "url": "https://semanariovoz.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://semanariovoz.com/feed/"],  # OJO: comparte piezas con pacocol (mismos slugs) -> dedup por hash de contenido
    },
    "desdeabajo": {
        "url": "https://www.desdeabajo.info",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.desdeabajo.info/feed/"],
    },
    "colombiaplural": {
        "url": "https://colombiaplural.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://colombiaplural.com/feed/"],  # OJO: el tema tagDiv inyecta CSS inline dentro de <p>
    },
    "verdadabierta": {
        "url": "https://verdadabierta.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://verdadabierta.com/feed/"],
    },
    "periferiaprensa": {
        "url": "https://periferiaprensa.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://periferiaprensa.com/feed/"],  # OJO: volumen bajo-medio
    },
    "notasobreras": {
        "url": "https://notasobreras.net",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://notasobreras.net/feed/"],
    },
    "elturbion": {
        "url": "https://elturbion.com",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://elturbion.com/feed/"],  # OJO: flujo nuevo bajo (el valor es el archivo 2007+) y duplica piezas en ES/EN
    },
    "baudoap": {
        "url": "https://baudoap.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://baudoap.com/feed/"],
    },
    "vokaribe": {
        "url": "https://www.vokaribe.net",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.vokaribe.net/feed/"],  # OJO: volumen bajo-medio; mezcla contenido sobre la emisora
    },
    "justiciaypaz": {
        "url": "https://www.justiciaypazcolombia.com",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.justiciaypazcolombia.com/feed/"],  # OJO: /sitemap_index.xml da 404, el válido es /wp-sitemap.xml
    },
    "movice": {
        "url": "https://movimientodevictimas.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://movimientodevictimas.org/feed/"],  # OJO: rutas multiidioma /es/ que pueden duplicar (normalizar en dedup)
    },
    "congresodelospueblos": {
        "url": "https://congresodelospueblos.org",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://congresodelospueblos.org/feed/"],  # OJO: comunicados cortos, vigilar el mínimo de longitud
    },
    "partidocomunes": {
        "url": "https://partidocomunes.com.co",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://partidocomunes.com.co/feed/"],  # OJO: sin posts nuevos desde oct-2025, el valor es el archivo (897 posts)
    },
    "polodemocratico": {
        "url": "https://www.polodemocratico.net",
        "category": "independiente",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.polodemocratico.net/feed/"],  # OJO: /sitemap.xml está VACÍO (usar sitemap_index.xml); sin publicar desde feb-2026
    },

    # --- Independientes: investigación transnacional y verificación ---
    "colombiacheck": {
        "url": "https://colombiacheck.com",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": ["/chequeos/", "/investigaciones/", "/investigaciones-especiales/"],
        "rss_feeds": ["https://colombiacheck.com/rss.xml"],  # OJO: sin sitemap; riesgo metodológico: el chequeo CITA la ideología ajena para refutarla
    },
    "elolfato": {
        "url": "https://elolfato.com",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": [
            "/poder/", "/investigacion/", "/justicia/", "/ibague/",
            "/region/", "/nacion/", "/opinion/", "/historias/",
        ],
        "rss_feeds": [],  # OJO: sin RSS y sitemap corto (128 URLs) -> volumen histórico bajo
    },
    "consonante": {
        "url": "https://consonante.org",
        "category": "independiente",
        "mode": "sitemap",
        "url_filters": ["/noticia/"],
        "rss_feeds": ["https://consonante.org/feed/"],  # OJO: excluir /formato/podcast y /formato/videos (sin cuerpo)
    },

    # --- Judicial / técnico-legal ---
    "cortesuprema": {
        "url": "https://cortesuprema.gov.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cortesuprema.gov.co/feed/"],  # OJO: el CMS legado /corte/index.php duplica notas -> dedup por título
    },
    "cndj": {
        "url": "https://cndj.gov.co/web/comision-nacional-de-disciplina-judicial/historico-de-noticias",
        "category": "judicial",
        "mode": "sitemap",
        "url_filters": ["/historico-de-noticias", "/asset_publisher/"],
        "rss_feeds": [],  # OJO: sin RSS y sitemap Liferay de layouts (inservible) -> crawl del histórico
    },
    "ramajudicial": {
        "url": "https://www.ramajudicial.gov.co/web/guest/historico-de-noticias",
        "category": "judicial",
        "mode": "sitemap",
        "url_filters": ["/historico-de-noticias", "/asset_publisher/"],
        "rss_feeds": [],  # OJO: infra lenta (504 intermitente), usar SIEMPRE www y subir timeout / bajar concurrencia
    },
    "asuntoslegales": {
        "url": "https://www.asuntoslegales.com.co",
        "category": "judicial",
        "mode": "sitemap",
        "url_filters": ["/actualidad/", "/analisis/", "/pleitos/", "/consumidor/", "/consultorio/"],
        "rss_feeds": ["https://www.asuntoslegales.com.co/rss"],  # OJO: excluir /edictos/ (boilerplate); sitemaps mensuales .xml.gz desde 2012
    },
    "blogderechoestado": {
        "url": "https://blogrevistaderechoestado.uexternado.edu.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS; textos con notas al pie que el cleaner no debe truncar
    },
    "notinetlegal": {
        "url": "https://www.notinetlegal.com",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS ni sitemap; mojibake en slugs y títulos; 2-5 piezas/semana
    },
    "actualicese": {
        "url": "https://actualicese.com",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [  # OJO: PAYWALL PARCIAL ('Exclusivo para suscriptores') y mucha nota contable sin carga política
            "https://actualicese.com/rss.xml",
            "https://actualicese.com/feed/",
        ],
    },
    "ccajar": {
        "url": "https://www.colectivodeabogados.org",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.colectivodeabogados.org/feed/"],
    },
    "ilex_aj": {
        "url": "https://ilexaccionjuridica.org",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ilexaccionjuridica.org/feed/"],  # OJO: volumen bajo; /sitemap_index.xml da 404, usar /wp-sitemap.xml
    },

    # --- Opinión / think tanks: economía, fiscal, riesgo, urbano ---
    "cedetrabajo": {
        "url": "https://cedetrabajo.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cedetrabajo.org/feed/"],
    },
    "ofiscal": {
        "url": "https://www.ofiscal.org",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/post/"],
        "rss_feeds": ["https://www.ofiscal.org/blog-feed.xml"],  # OJO: Wix, los <p> vienen vacíos (el texto sí está en el HTML); slugs con acentos
    },
    "probogota": {
        "url": "https://www.probogota.org",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/comunicacion_c/", "/publicaciones_c/"],
        "rss_feeds": [],  # OJO: el /feed/ solo trae perfiles de afiliados -> NO usarlo; excluir videos_probogota y podcasts
    },
    "bogotacomovamos": {
        "url": "https://bogotacomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://bogotacomovamos.org/feed/"],  # OJO: volumen bajo, pero textos largos
    },
    "colombiariskanalysis": {
        "url": "https://www.colombiariskanalysis.com",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/post/"],
        "rss_feeds": ["https://www.colombiariskanalysis.com/blog-feed.xml"],  # OJO: cada análisis está duplicado ES/EN y las piezas públicas son cortas (~1.2k chars)
    },

    # --- Opinión / think tanks: paz, conflicto, drogas, DDHH ---
    "indepaz": {
        "url": "https://indepaz.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://indepaz.org.co/feed/"],  # OJO: mucha producción en PDF; la portada está llena de /portfolio/ y /author/
    },
    "codhes": {
        "url": "https://codhes.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://codhes.org/feed/"],  # OJO: /sitemap_index.xml da 404, usar /wp-sitemap.xml
    },
    "capaz": {
        "url": "https://www.instituto-capaz.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.instituto-capaz.org/feed/"],  # OJO: ruido de convocatorias académicas y plazas administrativas
    },
    "cesed": {
        "url": "https://cesed.uniandes.edu.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cesed.uniandes.edu.co/feed/"],  # OJO: publica también en inglés y mucho evento/curso -> filtrar idioma
    },
    "visomutop": {
        "url": "https://visomutop.org",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": [],  # OJO: flujo casi detenido (feed con un solo item de 2026 y el resto de 2024) -> descubrir por sitemap
    },
    "somosdefensores": {
        "url": "https://somosdefensores.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://somosdefensores.org/feed/"],  # OJO: volumen bajo (227 posts históricos)
    },
    "temblores": {
        "url": "https://www.temblores.org",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/post/"],
        "rss_feeds": ["https://www.temblores.org/blog-feed.xml"],  # OJO: Wix (los 'Paywall' del HTML son boilerplate, no hay muro); volumen bajo
    },
    "coljuristas": {
        "url": "https://coljuristas.org/sala_de_prensa/",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/sala_de_prensa/", "/columnas_de_opinion", "/observatorio_jep/"],
        "rss_feeds": [],  # OJO: sin RSS; el sitemap emite <loc> relativos rotos ('..', 'whatsapp:') -> preferir crawl
    },
    "transparenciacolombia": {
        "url": "https://transparenciacolombia.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [  # /rss.xml trae 50 items (preferible al /feed/ de 10)
            "https://transparenciacolombia.org.co/rss.xml",
            "https://transparenciacolombia.org.co/feed/",
        ],
    },
    "cej": {
        "url": "https://cej.org.co",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/", "/destacado/", "/destacados-home-page/", "/publicaciones/"],
        "rss_feeds": ["https://cej.org.co/feed/"],  # OJO: excluir /infografias/ e /indicadores-de-justicia/ (fichas de datos)
    },

    # --- Opinión / think tanks: género, LGBTIQ+, izquierda doctrinaria, academia ---
    "sismamujer": {
        "url": "https://sismamujer.org",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": [],  # OJO: /feed/ congelado en 2021 y /rss.xml es sitemap-RSS; cuerpo en PDF -> textos muy cortos (~1.2k chars)
    },
    "caribeafirmativo": {
        "url": "https://www.caribeafirmativo.lgbt",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.caribeafirmativo.lgbt/feed/"],  # OJO: robots declara mal el sitemap (http, sin www) -> usar /wp-sitemap.xml
    },
    "corporacionregion": {
        "url": "https://region.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://region.org.co/feed/"],  # OJO: ~1 pieza al mes y el feed mezcla convocatorias laborales
    },
    "viva_ciudadania": {
        "url": "https://viva.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://viva.org.co/feed/"],  # OJO: solo 23 posts indexados (el archivo del Semanario Caja de Herramientas NO está aquí)
    },
    "revistasur": {
        "url": "https://www.sur.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.sur.org.co/feed/"],  # feed de 50 items y ~1MB: el de mayor rendimiento del lote
    },
    "kavilando": {
        "url": "https://kavilando.org/lineas-kavilando/",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/lineas-kavilando/"],
        "rss_feeds": [],  # OJO: sin RSS (el de Joomla está congelado en 2014) ni sitemap -> crawl dirigido por sección; evitar /libros/ y /component/
    },
    "obsdemocracia": {
        "url": "https://obsdemocracia.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://obsdemocracia.org/feed/"],  # OJO: ~10 notas en total; el resto del sitio son dashboards no extraíbles
    },
    "revistazero": {
        "url": "https://zero.uexternado.edu.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS; cadencia por números monotemáticos, volumen bajo (179 posts)
    },
    "unidosporlavida": {
        "url": "https://unidosporlavida.com",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://unidosporlavida.com/feed/"],  # OJO: volumen muy bajo (últimas piezas jun-2026)
    },
    "cec": {
        "url": "https://www.cec.org.co",
        "category": "opinion",
        "mode": "sitemap",
        "url_filters": ["/sistema-informativo/", "/tags/provida"],
        "rss_feeds": ["https://www.cec.org.co/rss.xml"],  # OJO: sin sitemap; mucho contenido eclesial (catequesis, nuncios) que el filtro descartará
    },
    "alponiente": {
        "url": "https://alponiente.com",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://alponiente.com/feed/"],  # OJO: 19.324 posts pero mezcla cultura, filosofía y literatura -> descarte apreciable
    },

    # --- Gremiales: agro y minero-energético (contrapeso conservador/soberanista) ---
    "contextoganadero": {
        "url": "https://www.contextoganadero.com",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/politica/", "/gremialidad/", "/columna/", "/economia/", "/editorial/"],
        "rss_feeds": [],  # OJO: sin RSS; requiere UA de navegador; el sitemap vive en el SUBDOMINIO sitemaps.contextoganadero.com
    },
    "fedegan": {
        "url": "https://www.fedegan.org.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/sala-de-prensa/"],
        "rss_feeds": [],  # OJO: /rss.xml existe pero solo lista indicadores de precio, no noticias -> no registrarlo; sin sitemap
    },
    "fenavi": {
        "url": "https://fenavi.org",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/centro-de-noticias/", "/comunicados-de-prensa/"],
        "rss_feeds": ["https://fenavi.org/feed/"],  # OJO: el feed está dominado por /contrataciones (términos de referencia) -> los filtros son imprescindibles
    },
    "fedepalma": {
        "url": "https://fedepalma.org",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/comunicados/"],
        "rss_feeds": ["https://fedepalma.org/feed/"],
    },
    "fedearroz": {
        "url": "https://www.fedearroz.com.co/es/",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/es/noticias/"],
        "rss_feeds": ["https://www.fedearroz.com.co/feed/"],  # OJO: sin sitemap -> crawl paginado de /es/noticias/?page=N; los <link> del feed vienen en http
    },
    "porkcolombia": {
        "url": "https://porkcolombia.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/comunicados/"],
        "rss_feeds": [],  # OJO: /feed/ es XML válido pero con 0 items; usar wp-sitemap-posts-noticias/comunicados
    },
    "fedecafeteros": {
        "url": "https://federaciondecafeteros.org",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/listado-noticias/"],
        "rss_feeds": [],  # OJO: sin RSS (feeds deshabilitados); ~59 notas útiles y hay que filtrar ?lang=en
    },
    "acmineria": {
        "url": "https://acmineria.com.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/blog/"],
        "rss_feeds": ["https://acmineria.com.co/feed/"],
    },
    "acp": {
        "url": "https://acp.com.co/portal/",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/portal/"],
        "rss_feeds": [],  # OJO: sin RSS y ~3 piezas/mes, mezcladas con PR corporativo de afiliadas
    },
    "campetrol": {
        "url": "https://campetrol.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://campetrol.org/feed/"],  # OJO: sin sitemap y densidad baja (mayoría 'CAMPETROL felicita a ...')
    },
    "naturgas": {
        "url": "https://naturgas.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://naturgas.com.co/feed/"],  # OJO: el archivo reproduce prensa sectorial internacional; la voz propia está en /category/comunicados/
    },
    "andesco": {
        "url": "https://andesco.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://andesco.org.co/feed/"],
    },
    "acolgen": {
        "url": "https://acolgen.org.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/portfolio/"],
        "rss_feeds": [],  # OJO: feed y post-sitemap CONGELADOS en 2022; el contenido vivo está en portfolio-sitemap.xml (y trae duplicados '-2')
    },
    "fenalcarbon": {
        "url": "https://fenalcarbon.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://fenalcarbon.org.co/feed/"],  # OJO: /sitemap_index.xml da 404, el válido es /wp-sitemap.xml
    },

    # --- Gremiales: industria, comercio, finanzas, salud, profesionales ---
    "camacol": {
        "url": "https://camacol.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/prensa/noticias/"],
        "rss_feeds": ["https://camacol.co/rss.xml"],  # OJO: sin sitemap y el feed está dominado por /descargable/ (decretos y circulares)
    },
    "acoplasticos": {
        "url": "https://acoplasticos.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://acoplasticos.org/feed/"],  # OJO: solo 43 posts, con placeholders lorem-ipsum y contenido comercial de pinturas
    },
    "fasecolda": {
        "url": "https://www.fasecolda.com",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.fasecolda.com/feed/"],
    },
    "asofondos": {
        "url": "https://asofondos.org.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/comunicados/"],
        "rss_feeds": ["https://asofondos.org.co/feed/"],  # OJO: requiere UA de navegador; el feed son informes de gestión y /comunicados/ tiene lastmod 2019-2021
    },
    "analdex": {
        "url": "https://analdex.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://analdex.org/feed/"],
    },
    "amcham": {
        "url": "https://amchamcolombia.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": [
            "/noticias-colombia/", "/noticias-observatorio-estados-unidos/",
            "/noticias-afiliados/", "/noticias-rse/",
        ],
        "rss_feeds": ["https://amchamcolombia.co/feed/"],  # OJO: los filtros dejan fuera /eventos-pasados y /amcham-en-medios (prensa de terceros)
    },
    "confecamaras": {
        "url": "https://confecamaras.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://confecamaras.org.co/feed/"],
    },
    "anato": {
        "url": "https://anato.org",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/noticias/"],
        "rss_feeds": ["https://anato.org/noticias/feed/"],  # OJO: el /feed/ raíz tiene 0 items y /rss.xml es un sitemap, no un feed
    },
    "acemi": {
        "url": "https://acemi.org.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/"],
        "rss_feeds": ["https://acemi.org.co/feed/"],  # OJO: ~7 artículos en todo el dominio; 2 de los 3 items del feed son recortes de terceros
    },
    "achc": {
        "url": "https://achc.org.co/actualidad/",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": ["/actualidad/", "/boletines-y-comunicados-achc/"],
        "rss_feeds": [],  # OJO: feed y sitemap congelados en 2022 aunque /actualidad/ sí está fresco -> crawl paginado; excluir /achc-en-los-medios/
    },
    "sci_ingenieros": {
        "url": "https://sci.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://sci.org.co/feed/"],  # OJO: mucho ruido de cursos y seminarios (posts en slug raíz, no se puede filtrar por path); excluir /feed/podcast
    },
    "ascun": {
        "url": "https://ascun.org.co",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": [
            "/noticias-ascun/", "/educacion-superior/",
            "/columna-de-opinion-voces-de-la-educacion-superior/",
        ],
        "rss_feeds": ["https://ascun.org.co/feed/"],  # OJO: ~85% del archivo es /noticias-ies/ (acreditaciones sin carga ideológica) -> filtros obligatorios
    },
    "acore": {
        "url": "https://www.acore.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.acore.org.co/feed/"],  # OJO: mezcla columnas con avisos internos (talleres, NotiACORE)
    },
    "cedecol": {
        "url": "https://cedecol.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cedecol.org/feed/"],  # OJO: ~10 posts en total y varios con el cuerpo en PDF (caen por debajo de min_chars)
    },

    # --- Gremiales: sindicatos y organizaciones étnicas/campesinas ---
    "ctc": {
        "url": "https://ctc-colombia.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ctc-colombia.com.co/feed/"],  # OJO: usar host SIN www; robots.txt declara un sitemap de dev, el válido es /sitemap_index.xml
    },
    "uso": {
        "url": "https://www.uso.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.uso.org.co/feed/"],  # OJO: buena parte del sitio son servicios al afiliado (liquidaciones, mapas de cargos)
    },
    "anthoc": {
        "url": "https://www.anthoc.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.anthoc.org/feed/"],  # OJO: el apex redirige a www; /index.xml es un sitemapindex, no un feed
    },
    "adida": {
        "url": "https://adida.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://adida.org.co/feed/"],  # OJO: 64 posts en total y feed de 4 items sobre una sola campaña
    },
    "cna_colombia": {
        "url": "https://cnacolombia.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cnacolombia.org/feed/"],  # OJO: /rss.xml es sitemap-RSS de All in One SEO (sin pubDate), no usarlo
    },
    "anuc": {
        "url": "https://anucnacional.com",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://anucnacional.com/feed/"],  # OJO: volumen bajo y ruido administrativo (convocatorias de suministros)
    },
    "cric": {
        "url": "https://www.cric-colombia.org/portal",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.cric-colombia.org/portal/feed/"],  # la raíz real es /portal/ (en el apex el feed da 404)
    },
    "nasaacin": {
        "url": "https://nasaacin.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://nasaacin.org/feed/"],  # OJO: feed stale (jun-2026) y flujo reciente administrativo (actas, licitaciones)
    },
    "onic": {
        "url": "https://www.onic.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.onic.org.co/feed/"],  # OJO: volumen irregular; /rss.xml, /index.xml y /sitemap_index.xml son catch-all que sirven la portada
    },
    "renacientes": {
        "url": "https://renacientes.net",
        "category": "gremial",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": [],  # OJO: NO tiene RSS (los /feed/ sirven la portada en HTML) -> descubrimiento por sitemap_index.xml
    },
    "cococauca": {
        "url": "https://cococauca.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cococauca.org/feed/"],  # OJO: volumen muy bajo y mezcla décimas y obituarios con denuncias políticas
    },

    # --- Institucionales: gobierno de Bogotá (vacío local del corpus) ---
    "bogotadistrito": {
        "url": "https://bogota.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": [
            "/mi-ciudad/gobierno/", "/mi-ciudad/seguridad/",
            "/mi-ciudad/administracion-distrital/", "/mi-ciudad/localidades/",
            "/mi-ciudad/movilidad/", "/mi-ciudad/ambiente/",
            "/mi-ciudad/desarrollo-economico/", "/mi-ciudad/hacienda/",
            "/mi-ciudad/salud/",
        ],
        "rss_feeds": [],  # OJO: /rss.xml es válido pero sus items son solo /boletin-oferta-internacional/ (becas) -> ruido; lastmod del sitemap desactualizado
    },
    "concejobogota": {
        "url": "https://concejodebogota.gov.co/cbogota/site/edic/base/port/prensa.php",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: la raíz es solo un meta-refresh; sembrar prensa.php. Sin RSS y sitemap con <loc> malformados
    },
    "personeriabogota": {
        "url": "https://www.personeriabogota.gov.co/sala-de-prensa/notas-de-prensa",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/notas-de-prensa"],
        "rss_feeds": [],  # OJO: sin RSS (feed con 0 items) ni sitemap útil (osmap con 1 loc); cadencia baja
    },
    "canalcapital": {
        "url": "https://www.canalcapital.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/actualidad/", "/general/", "/ahora/"],
        "rss_feeds": ["https://www.canalcapital.gov.co/feed/"],  # OJO: /general/ mezcla parrilla, farándula y sucesos
    },

    # --- Institucionales: ministerios ---
    "minjusticia": {
        "url": "https://www.minjusticia.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/Sala-de-prensa/Paginas/"],
        "rss_feeds": [],  # OJO: sin RSS ni sitemap; el listado Noticias.aspx está roto -> crawl desde la home (volumen bajo por corrida)
    },
    "minsalud": {
        "url": "https://www.minsalud.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/Comunicaciones/noticias/"],
        "rss_feeds": [],  # OJO: sitemap0.xml VACÍO y listados en JS; las noticias viven en subsitios anuales /Comunicaciones/noticias/{YYYY}/Paginas/
    },
    "mineducacion": {
        "url": "https://www.mineducacion.gov.co/portal/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/portal/salaprensa/Noticias/"],
        "rss_feeds": [],  # OJO: hay que entrar por el sitemap (la URL de listado da 404); excluir Videos/Fotos/Audios
    },
    "mintrabajo": {
        "url": "https://www.mintrabajo.gov.co/prensa/comunicados",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/comunicados/", "/prensa/comunicados/"],
        "rss_feeds": [],  # OJO: Liferay MUY lento (timeouts a 25-40s) y sitemap con 3.191 hijos -> inviable, usar el archivo por año-mes
    },
    "minagricultura": {
        "url": "https://www.minagricultura.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/el-ministerio/sala-de-p/noticias/"],
        "rss_feeds": [],  # OJO: el sitemap TYPO3 solo trae el hub de noticias -> crawl del listado
    },
    "minenergia": {
        "url": "https://www.minenergia.gov.co/es/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/es/sala-de-prensa/noticias-index/"],
        "rss_feeds": [],  # OJO: sin sitemap ni RSS; URLs con acentos percent-encoded (normalizar antes del dedup)
    },
    "minambiente": {
        "url": "https://www.minambiente.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.minambiente.gov.co/feed/"],  # OJO: posts en la raíz; usar los 3 post-sitemap y NO el hub /sala-de-prensa/ (JS)
    },
    "mincit": {
        "url": "https://www.mincit.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/prensa/noticias/general/", "/prensa/noticias/industria/", "/prensa/noticias/comercio/"],
        "rss_feeds": [],  # OJO: el sitemap real es /googlesitemap.xml (/sitemap.xml es una página HTML); excluir /prensa/video-noticias y /turismo/
    },
    "mintransporte": {
        "url": "https://mintransporte.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/publicaciones/"],
        "rss_feeds": ["https://mintransporte.gov.co/rss"],  # URLs numéricas: tomar el título del HTML
    },
    "mintic": {
        "url": "https://mintic.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/portal/inicio/Sala-de-prensa/Noticias/", "/portal/inicio/Sala-de-Prensa/Noticias/"],
        "rss_feeds": [],  # OJO: host canónico SIN www; mayúsculas inconsistentes en 'Sala-de-prensa' -> normalizar para dedup; robots.txt da 403
    },
    "minvivienda": {
        "url": "https://www.minvivienda.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/"],
        "rss_feeds": [],  # OJO: los <loc> vienen sin www -> normalizar; sitemap paginado ?page=1..24 con histórico hasta 2013
    },
    "mincultura": {
        "url": "https://www.mincultura.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias/Paginas/"],
        "rss_feeds": [],  # OJO: los <loc> traen ':443' -> normalizar; el hub /noticias es un listado JS
    },
    "minciencias": {
        "url": "https://minciencias.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/sala_de_prensa/", "/pagina-de-contenidos/noticias"],
        "rss_feeds": ["https://minciencias.gov.co/rss.xml"],  # dominio canónico SIN www
    },
    "mindeporte": {
        "url": "https://www.mindeporte.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/noticias-mindeporte/", "/sala-de-prensa/archivo-noticias/"],
        "rss_feeds": [],  # OJO: 10.740 URLs pero mayoría resultados deportivos -> valor ideológico bajo, prioridad mínima
    },
    "minigualdad": {
        "url": "https://www.minigualdadyequidad.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/-/", "/noticias/"],
        "rss_feeds": [],  # OJO: ministerio EN LIQUIDACIÓN -> cosechar el histórico ya; quitar ?redirect= antes de deduplicar
    },

    # --- Institucionales: agencias, superintendencias y órganos de control ---
    "dnp": {
        "url": "https://www.dnp.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/Prensa_/Noticias/Paginas/"],
        "rss_feeds": [],  # OJO: ojo al guion bajo en 'Prensa_' y al ':443' de los <loc>; el hub es un listado JS
    },
    "dian": {
        "url": "https://www.dian.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/Prensa/Paginas/"],
        "rss_feeds": [],  # OJO: sin sitemap ni robots; comunicados enumerables NG-Comunicado-de-Prensa-<NNN>-<anio>.aspx con 3 dígitos
    },
    "supersociedades": {
        "url": "https://www.supersociedades.gov.co/noticias-supersociedades",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias-supersociedades", "/asset_publisher/"],
        "rss_feeds": [],  # OJO: sitemap Liferay sin noticias; las URLs solo aparecen en los enlaces de compartir (/-/asset_publisher/atwl/content/<slug>)
    },
    "anla": {
        "url": "https://www.anla.gov.co/noticias-anla/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias-anla/"],
        "rss_feeds": [],  # OJO: sin sitemap ni RSS; la ruta es /noticias-anla/ (no /noticias)
    },
    "anh": {
        "url": "https://www.anh.gov.co/es/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/es/noticias/"],
        "rss_feeds": [],  # OJO: los <loc> vienen como http://anh.gov.co (sin https ni www) y con acentos -> normalizar o el fetch expira
    },
    "ani": {
        "url": "https://www.ani.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/w/"],
        "rss_feeds": [],  # OJO: 193 sub-sitemaps; excluir los /xx/search de los 30+ prefijos de idioma y normalizar percent-encoding
    },
    "icbf": {
        "url": "https://www.icbf.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias"],
        "rss_feeds": [],  # OJO: cadena TLS INCOMPLETA (CERTIFICATE_VERIFY_FAILED) -> incluir solo si el fetcher relaja la verificación para este dominio
    },
    "migracioncolombia": {
        "url": "https://portal.migracioncolombia.gov.co/agenda-migcol/comunicaciones-y-prensa",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/detalle-noticia/agenda-migcol/comunicaciones-y-prensa/"],
        "rss_feeds": [],  # OJO: usar el host portal.* y BLOQUEAR www.* (SPA Angular sin texto); mucho contenido operativo
    },
    "defensoria": {
        "url": "https://www.defensoria.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/-/"],
        "rss_feeds": [],  # OJO: normalizar las dos variantes /-/<slug> y /web/guest/-/<slug>?redirect=... antes de deduplicar
    },
    "cne": {
        "url": "https://www.cne.gov.co/noticias-cne",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias-cne/", "/prensa/comunicados-oficiales/"],
        "rss_feeds": [],  # OJO: sin sitemap; archivo por año paginable con ?start=N
    },
    "auditoria": {
        "url": "https://www.auditoria.gov.co/web/guest/noticias-2026",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": [
            "/web/guest/noticias-",
            "/web/guest/gestion-del-conocimiento/repositorio-historico-de-noticias",
            "/asset_publisher/",
        ],
        "rss_feeds": [],  # OJO: sitemap Liferay de layouts (inservible) y volumen bajo (~8 notas en 2026)
    },
    "unidadvictimas": {
        "url": "https://www.unidadvictimas.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.unidadvictimas.gov.co/feed/"],  # OJO: apuntar SOLO a post-sitemap*.xml; el índice trae miles de registros administrativos
    },
    "renovacionterritorio": {
        "url": "https://www.renovacionterritorio.gov.co/noticias",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias/"],
        "rss_feeds": [],  # OJO: /rss.xml existe pero son documentos administrativos con pubDate falsas (2028-2029) -> no usarlo; dedup /index.php/noticias
    },
    "urt": {
        "url": "https://urt.gov.co/sala-de-prensa",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/sala-de-prensa/"],
        "rss_feeds": [],  # OJO: infra inestable (la raíz alterna 200/500); host SIN www, timeout alto y reintentos
    },
    "ant": {
        "url": "https://www.ant.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/prensa/noticias"],
        "rss_feeds": ["https://www.ant.gov.co/rss.xml"],  # OJO: el RSS mezcla noticias con /node/NNNN viejos -> los filtros son necesarios
    },
    "unidadbusqueda": {
        "url": "https://unidadbusqueda.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/actualidad/", "/comunicados/"],
        "rss_feeds": ["https://unidadbusqueda.gov.co/feed/"],  # host canónico SIN www; volumen bajo
    },
    "cnmh": {
        "url": "https://centrodememoriahistorica.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://centrodememoriahistorica.gov.co/feed/"],  # OJO: usar wp-sitemap-posts-post-1/2.xml y evitar los sitemaps de event/location/investigaciones
    },
    "defensajuridica": {
        "url": "https://www.defensajuridica.gov.co/category/noticias/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/category/noticias/"],
        "rss_feeds": [],  # OJO: sin RSS; el post-sitemap mezcla resoluciones y estados contables -> crawlear la sección, no el sitemap crudo
    },

    # --- Institucionales: fuerza pública ---
    "policia": {
        "url": "https://www.policia.gov.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticia/"],
        "rss_feeds": [],  # OJO: sitemap roto (un solo <loc> http://default/) y /rss.xml lista páginas de directorio -> no usarlo; mucho contenido operativo regional
    },
    "ejercito": {
        "url": "https://www.ejercito.mil.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.ejercito.mil.co/rss.xml"],  # artículos en la raíz; el news-sitemap.xml (334 locs) es 100% noticias. Dominio .mil.co
    },
    "fac": {
        "url": "https://www.fac.mil.co/es/noticias/",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/es/noticias/"],
        "rss_feeds": ["https://www.fac.mil.co/rss.xml"],  # OJO: el RSS mezcla avisos administrativos /es/node/NNNNN; densidad ideológica media-baja
    },

    # --- Institucionales: organismos internacionales con mandato en Colombia ---
    "onudh": {
        "url": "https://www.hchr.org.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": [
            "/comunicados/", "/historias_destacadas/", "/pronunciamientos/",
            "/informes_anuales/", "/informes_tematicos/", "/informes_onu/",
        ],
        "rss_feeds": [],  # OJO: usar SIEMPRE www; cadena TLS incompleta; /feed/ con 0 items y wp-sitemap.xml devuelve 501; muchos informes en PDF
    },

    # --- Institucionales: partidos y movimientos (voz de aparato) ---
    "partidoconservador": {
        "url": "https://partidoconservador.com",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://partidoconservador.com/feed/"],  # OJO: ~1 pieza al mes (148 posts en total)
    },
    "cambioradical": {
        "url": "https://www.partidocambioradical.org",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.partidocambioradical.org/feed/"],  # OJO: el índice trae sitemaps de cursos, eventos y certificados (escuela de formación)
    },
    "partidodelau": {
        "url": "https://www.partidodelau.com",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticia/", "/opinion-de-lider/"],
        "rss_feeds": [],  # OJO: el /feed/ solo trae banners y landings -> NO registrarlo; volumen bajo (~75 piezas)
    },
    "nuevoliberalismo": {
        "url": "https://nuevoliberalismo.org",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],  # OJO: sin RSS y solo ~2 artículos reales (el resto del sitemap son PDFs y páginas institucionales)
    },
    "alianzaverde": {
        "url": "https://alianzaverde.org.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://alianzaverde.org.co/feed/"],  # OJO: SIN sitemap -> depende del RSS (10 items rotativos) y del crawl; se pierde histórico
    },
    "pactohistorico": {
        "url": "https://www.movimientopactohistorico.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias/"],
        "rss_feeds": [],  # OJO: sin RSS y solo 28 notas reales (el resto del sitemap son /candidatos y /100logros)
    },
    "unionpatriotica": {
        "url": "https://partido-up.org",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://partido-up.org/feed/"],  # OJO: ignorar image-sitemap/video-sitemap; solapa temáticamente con pacocol y semanariovoz
    },
    "pacocol": {
        "url": "https://pacocol.org",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://pacocol.org/feed/"],  # OJO: 7.168 posts y varias piezas al día, pero DUPLICA slugs con semanariovoz -> dedup por hash obligatorio
    },
    "partidomira": {
        "url": "https://partidomira.com",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://partidomira.com/feed/"],
    },
    "dignidadycompromiso": {
        "url": "https://dignidadycompromiso.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://dignidadycompromiso.co/feed/"],  # OJO: /sitemap_index.xml da 404, el válido es /wp-sitemap.xml
    },
    "mais": {
        "url": "https://mais.com.co",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/noticias/"],
        "rss_feeds": ["https://mais.com.co/feed/"],  # OJO: mayoría comunicados repetidos y circulares administrativas -> densidad por documento baja
    },
    "soyliga": {
        "url": "https://soyliga.org/blog",
        "category": "institucional",
        "mode": "sitemap",
        "url_filters": ["/blog/"],
        "rss_feeds": [],  # OJO: sin RSS y solo 7 artículos; el sitemap son calculadoras financieras -> crawl de /blog
    },

    # =======================================================================
    # AMPLIACION 4 — estratos de actor territorial (ronda 2)
    #
    # Cierra los tres estratos que el catalogo no tenia: ejecutivo territorial
    # (gobernaciones y alcaldias), deliberativo territorial (asambleas y
    # concejos) y asociaciones de gobiernos. Mas TV/radio publica y regionales
    # que estaban en cero.
    #
    # Verificadas con scripts/verify_sources.py, que corre TRAFILATURA sobre un
    # articulo de muestra: un "include" significa que el pipeline real extrae
    # texto, no que la portada respondio 200. De 283 candidatos entraron 147.
    # Descartes: 45 con el cuerpo renderizado en cliente (la plataforma Angular
    # de MinTIC que usan los departamentos pequenos devuelve un shell de 2.905
    # bytes), 14 mega-paginas sin URL por articulo, 13 caidos o con WAF.
    #
    # NO SE REGISTRAN 32 dominios que rechazan el uso de su contenido para
    # entrenar modelos (Content-Signal ai-train=no o Disallow para GPTBot y
    # similares). Es una decision de consentimiento y esta documentada en el
    # script; ver --allow-ai-blocked si el director decide otra cosa.
    #
    # Tampoco entran 22 think tanks liberales y medios catolicos de Espana,
    # Argentina y Chile: cerrarian el hueco de doctrinarismo de mercado con
    # texto NO colombiano y el modelo aprenderia el espanol peninsular como
    # proxy de la clase.
    # =======================================================================

    "ail": {
        "url": "https://ail.ens.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ail.ens.org.co/comments/feed/", "https://ail.ens.org.co/feed/"],
    },
    "ami": {
        "url": "https://ami.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "andemos": {
        "url": "https://www.andemos.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.andemos.org/blog-feed.xml"],
    },
    "asocars": {
        "url": "https://www.asocars.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.asocars.org/comments/feed/", "https://www.asocars.org/feed/"],
    },
    "asocolflores": {  # OJO: cuerpo corto en la muestra
        "url": "https://asocolflores.org",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://asocolflores.org/feed/", "https://asocolflores.org/feed/"],
    },
    "asofiduciarias": {
        "url": "https://www.asofiduciarias.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "camarabaq": {
        "url": "https://www.camarabaq.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "camaramedellin": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.camaramedellin.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "camlibro": {
        "url": "https://camlibro.com.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://camlibro.com.co/feed/", "https://camlibro.com.co/feed/"],
    },
    "ccb": {
        "url": "https://www.ccb.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "ccce": {
        "url": "https://ccce.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ccce.org.co/feed/", "https://ccce.org.co/feed/"],
    },
    "colombiafintech": {
        "url": "https://colombiafintech.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://colombiafintech.co/feed/", "https://colombiafintech.co/feed/"],
    },
    "fedebiocombustibles": {
        "url": "https://fedebiocombustibles.com",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://fedebiocombustibles.com/feed/", "https://fedebiocombustibles.com/feed/"],
    },
    "incp": {  # OJO: cuerpo corto en la muestra
        "url": "https://incp.org.co",
        "category": "gremial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://incp.org.co/comments/feed/", "https://incp.org.co/feed/"],
    },
    "alcaldiaarauca": {  # OJO: cuerpo corto en la muestra
        "url": "https://arauca-arauca.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiacucuta": {
        "url": "https://cucuta.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cucuta.gov.co/feed/", "https://cucuta.gov.co/feed/"],
    },
    "alcaldiagiron": {  # OJO: cuerpo corto en la muestra
        "url": "https://giron-santander.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiaibague": {
        "url": "https://ibague.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiainirida": {  # OJO: cuerpo corto en la muestra
        "url": "https://inirida-guainia.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiaitagui": {
        "url": "https://itagui.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiamanizales": {
        "url": "https://centrodeinformacion.manizales.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://centrodeinformacion.manizales.gov.co/feed/", "https://centrodeinformacion.manizales.gov.co/feed/"],
    },
    "alcaldiapalmira": {
        "url": "https://palmira.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://palmira.gov.co/comments/feed/", "https://palmira.gov.co/feed/"],
    },
    "alcaldiapuertocarreno": {
        "url": "https://puertocarreno-vichada.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiariohacha": {
        "url": "https://riohacha-laguajira.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiarionegro": {
        "url": "https://rionegro.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiasincelejo": {
        "url": "https://alcaldiadesincelejo.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alcaldiavillavicencio": {
        "url": "https://villavicencio.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://villavicencio.gov.co/feed/", "https://villavicencio.gov.co/feed/"],
    },
    "ambarranquilla": {
        "url": "https://www.ambq.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.ambq.gov.co/feed/", "https://www.ambq.gov.co/feed/"],
    },
    "ambucaramanga": {
        "url": "https://www.amb.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.amb.gov.co/feed/", "https://www.amb.gov.co/feed/"],
    },
    "amcucuta": {  # OJO: cuerpo corto en la muestra
        "url": "https://amc.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://amc.gov.co/amc/feed/", "https://amc.gov.co/amc/feed/"],
    },
    "asamblea_antioquia": {  # OJO: cuerpo corto en la muestra
        "url": "https://asambleadeantioquia.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "asamblea_atlantico": {  # OJO: cuerpo corto en la muestra
        "url": "https://asamblea-atlantico.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://asamblea-atlantico.gov.co/feed/", "https://asamblea-atlantico.gov.co/feed/"],
    },
    "asamblea_bolivar": {
        "url": "https://www.asambleadebolivar.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.asambleadebolivar.gov.co/comments/feed/", "https://www.asambleadebolivar.gov.co/feed/"],
    },
    "asamblea_choco": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.asambleachoco.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.asambleachoco.gov.co/web/feed/", "https://www.asambleachoco.gov.co/web/feed/"],
    },
    "asamblea_cordoba": {
        "url": "https://asamblea-cordoba.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://asamblea-cordoba.gov.co/comments/feed/", "https://asamblea-cordoba.gov.co/feed/"],
    },
    "asamblea_santander": {
        "url": "https://asambleadesantander.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://asambleadesantander.gov.co/feed/", "https://asambleadesantander.gov.co/feed/"],
    },
    "asomunicipios": {
        "url": "https://asomunicipios.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://asomunicipios.gov.co/feed/", "https://asomunicipios.gov.co/feed/"],
    },
    "cabal": {
        "url": "https://mariafernandacabal.com",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://mariafernandacabal.com/feed/", "https://mariafernandacabal.com/feed/"],
    },
    "canalinstitucional": {
        "url": "https://www.canalinstitucional.tv",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "carder": {
        "url": "https://www.carder.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.carder.gov.co/comments/feed/", "https://www.carder.gov.co/feed/"],
    },
    "carsucre": {  # OJO: cuerpo corto en la muestra
        "url": "https://carsucre.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://carsucre.gov.co/comments/feed/"],
    },
    "cas_santander": {
        "url": "https://www.cas.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "concejobarrancabermeja": {
        "url": "https://concejobarrancabermeja.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejobarrancabermeja.gov.co/feed/", "https://concejobarrancabermeja.gov.co/feed/"],
    },
    "concejobucaramanga": {
        "url": "https://www.concejodebucaramanga.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "concejobuenaventura": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.concejobuenaventura.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "concejocartagena": {
        "url": "https://concejodistritaldecartagena.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejodistritaldecartagena.gov.co/comments/feed/", "https://concejodistritaldecartagena.gov.co/feed/"],
    },
    "concejocartago": {
        "url": "https://www.concejodecartago.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.concejodecartago.gov.co/feed/", "https://www.concejodecartago.gov.co/feed/"],
    },
    "concejocucuta": {
        "url": "https://www.concejocucuta.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.concejocucuta.gov.co/feed/", "https://www.concejocucuta.gov.co/feed/"],
    },
    "concejodosquebradas": {
        "url": "https://www.concejodedosquebradas.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.concejodedosquebradas.gov.co/feed/", "https://www.concejodedosquebradas.gov.co/feed/"],
    },
    "concejoenvigado": {  # OJO: cuerpo corto en la muestra
        "url": "https://concejoenvigado.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejoenvigado.gov.co/feed/", "https://concejoenvigado.gov.co/feed/"],
    },
    "concejogalapa": {  # OJO: cuerpo corto en la muestra
        "url": "https://concejodegalapa.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejodegalapa.gov.co/feed/", "https://concejodegalapa.gov.co/feed/"],
    },
    "concejomedellin": {
        "url": "https://www.concejodemedellin.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.concejodemedellin.gov.co/feed/", "https://www.concejodemedellin.gov.co/feed/"],
    },
    "concejopalmira": {
        "url": "https://concejopalmira.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejopalmira.gov.co/index.php/noticias?format=feed&amp;type=atom", "https://concejopalmira.gov.co/index.php/noticias?format=feed&amp;type=rss"],
    },
    "concejopasto": {
        "url": "https://concejodepasto.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejodepasto.gov.co/feed/", "https://concejodepasto.gov.co/feed/"],
    },
    "concejopereira": {
        "url": "https://concejopereira.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejopereira.gov.co/es/rss.xml"],
    },
    "concejopitalito": {
        "url": "https://concejopitalito.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejopitalito.gov.co/contenido/feed/"],
    },
    "concejosabaneta": {  # OJO: cuerpo corto en la muestra
        "url": "https://concejodesabaneta.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "concejovalledupar": {
        "url": "https://concejodevalledupar.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://concejodevalledupar.gov.co/feed/", "https://concejodevalledupar.gov.co/feed/"],
    },
    "contraloriaatlantico": {
        "url": "https://contraloriadelatlantico.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://contraloriadelatlantico.gov.co/index.php?format=feed&amp;type=atom", "https://contraloriadelatlantico.gov.co/index.php?format=feed&amp;type=rss"],
    },
    "contraloriabuenaventura": {
        "url": "https://www.contraloriabuenaventura.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.contraloriabuenaventura.gov.co/informacion-al-ciudadano/noticias?format=feed&amp;type=atom", "https://www.contraloriabuenaventura.gov.co/informacion-al-ciudadano/noticias?format=feed&amp;type=rss"],
    },
    "contraloriacartagena": {
        "url": "https://contraloriadecartagena.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://contraloriadecartagena.gov.co/feed/", "https://contraloriadecartagena.gov.co/feed/"],
    },
    "contraloriamagdalena": {
        "url": "https://contraloriadelmagdalena.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://contraloriadelmagdalena.gov.co/feed/", "https://contraloriadelmagdalena.gov.co/feed/"],
    },
    "cornare": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.cornare.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.cornare.gov.co/comments/feed/", "https://www.cornare.gov.co/feed/"],
    },
    "corpoguajira": {  # OJO: cuerpo corto en la muestra
        "url": "https://corpoguajira.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://corpoguajira.gov.co/feed/", "https://corpoguajira.gov.co/feed/"],
    },
    "corpoguavio": {
        "url": "https://www.corpoguavio.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.corpoguavio.gov.co/feed/", "https://www.corpoguavio.gov.co/feed/"],
    },
    "corponarino": {
        "url": "https://corponarino.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://corponarino.gov.co/feed/", "https://corponarino.gov.co/feed/"],
    },
    "corpouraba": {
        "url": "https://corpouraba.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://corpouraba.gov.co/feed/", "https://corpouraba.gov.co/feed/"],
    },
    "cra_atlantico": {
        "url": "https://www.crautonoma.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.crautonoma.gov.co/feed", "https://www.crautonoma.gov.co/feed"],
    },
    "cvc_valle": {
        "url": "https://cvc.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cvc.gov.co/rss.xml"],
    },
    "cvs_cordoba": {
        "url": "https://cvs.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cvs.gov.co/feed/", "https://cvs.gov.co/feed/"],
    },
    "fnd": {
        "url": "https://fnd.org.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "gob_antioquia": {
        "url": "https://www.antioquia.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.antioquia.gov.co/index.php/prensa?format=feed&amp;type=atom", "https://www.antioquia.gov.co/index.php/prensa?format=feed&amp;type=rss"],
    },
    "gob_arauca": {
        "url": "https://arauca.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://arauca.gov.co/feed/", "https://arauca.gov.co/feed/"],
    },
    "gob_bolivar": {
        "url": "https://www.bolivar.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.bolivar.gov.co/web/feed/", "https://www.bolivar.gov.co/web/feed/"],
    },
    "gob_caldas": {
        "url": "https://caldas.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://caldas.gov.co/noticias-gobernacion?format=feed&amp;type=atom", "https://caldas.gov.co/noticias-gobernacion?format=feed&amp;type=rss"],
    },
    "gob_narino": {  # OJO: cuerpo corto en la muestra
        "url": "https://narino.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://narino.gov.co/feed/", "https://narino.gov.co/feed/"],
    },
    "gob_sanandres": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.sanandres.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.sanandres.gov.co/feed/", "https://www.sanandres.gov.co/feed/"],
    },
    "inravision": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.inravision.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.inravision.gov.co/rss.xml"],
    },
    "mitu_vaupes": {
        "url": "https://mitu-vaupes.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "personeriabarranquilla": {
        "url": "https://personeriadebarranquilla.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://personeriadebarranquilla.gov.co/feed/", "https://personeriadebarranquilla.gov.co/feed/"],
    },
    "personeriacali": {
        "url": "https://personeriacali.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://personeriacali.gov.co/feed/", "https://personeriacali.gov.co/feed/"],
    },
    "personeriaitagui": {
        "url": "https://personeriaitagui.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "rapcaribe": {  # OJO: archivo pequeno
        "url": "https://rapcaribe.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://rapcaribe.gov.co/feed/", "https://rapcaribe.gov.co/feed/"],
    },
    "rapecentral": {  # OJO: cuerpo corto en la muestra
        "url": "https://regioncentralrape.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://regioncentralrape.gov.co/feed/", "https://regioncentralrape.gov.co/feed/"],
    },
    "rtvcnoticias": {
        "url": "https://www.rtvcnoticias.com",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.rtvcnoticias.com/rss.xml"],
    },
    "telecaribe": {
        "url": "https://telecaribe.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://telecaribe.co/comments/feed/", "https://telecaribe.co/feed/"],
    },
    "telemedellin": {
        "url": "https://telemedellin.tv",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://telemedellin.tv/tipo/noticias/feed/", "https://telemedellin.tv/feed/"],
    },
    "icdt": {
        "url": "https://icdt.co",
        "category": "judicial",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://icdt.co/feed/", "https://icdt.co/feed/"],
    },
    "colmundoradio": {
        "url": "https://colmundoradio.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://colmundoradio.com.co/feed/", "https://colmundoradio.com.co/feed/"],
    },
    "lanotaeconomica": {
        "url": "https://lanotaeconomica.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://lanotaeconomica.com.co/feed/", "https://lanotaeconomica.com.co/feed/"],
    },
    "misionpyme": {
        "url": "https://misionpyme.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/noticias/", "/pymes-4-0/", "/gacelas/", "/formacion/"],
        "rss_feeds": [],
    },
    "noticiasrcn": {
        "url": "https://www.noticiasrcn.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/colombia/", "/internacional/", "/economia/", "/tendencias/"],
        "rss_feeds": [],
    },
    "noticiasuno": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.noticiasuno.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/nacional/", "/economia/", "/internacional/", "/justicia/", "/politica/"],
        "rss_feeds": ["https://www.noticiasuno.com/feed/", "https://www.noticiasuno.com/feed/"],
    },
    "sectorial": {
        "url": "https://sectorial.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/articulos-especiales/"],
        "rss_feeds": [],
    },
    "wradio": {
        "url": "https://www.wradio.com.co",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/programas/"],
        "rss_feeds": [],
    },
    "barranquillacomovamos": {  # OJO: cuerpo corto en la muestra
        "url": "https://barranquillacomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://barranquillacomovamos.org/feed/", "https://barranquillacomovamos.org/feed/"],
    },
    "buenaventuracomovamos": {
        "url": "https://www.buenaventuracomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.buenaventuracomovamos.org/feed/", "https://www.buenaventuracomovamos.org/feed/"],
    },
    "bvirtualbarranca": {
        "url": "https://barrancabermejavirtual.com",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://barrancabermejavirtual.com/feed/", "https://barrancabermejavirtual.com/feed/"],
    },
    "calicomovamos": {
        "url": "https://www.calicomovamos.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.calicomovamos.org.co/blog-feed.xml"],
    },
    "cartagenacomovamos": {
        "url": "https://cartagenacomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cartagenacomovamos.org/feed/", "https://cartagenacomovamos.org/feed/"],
    },
    "compite": {
        "url": "https://compite.com.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://compite.com.co/feed/", "https://compite.com.co/feed/"],
    },
    "cristovision": {
        "url": "https://cristovision.tv",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://cristovision.tv/rss.xml"],
    },
    "emisoramariana": {  # OJO: archivo pequeno
        "url": "https://emisoramariana.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "ibaguecomovamos": {  # OJO: cuerpo corto en la muestra
        "url": "https://ibaguecomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://ibaguecomovamos.org/feed/", "https://ibaguecomovamos.org/feed/"],
    },
    "manizalescomovamos": {
        "url": "https://manizalescomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://manizalescomovamos.org/feed/", "https://manizalescomovamos.org/feed/"],
    },
    "medellincomovamos": {
        "url": "https://www.medellincomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.medellincomovamos.org/feed/", "https://www.medellincomovamos.org/feed/"],
    },
    "novaetvetera": {
        "url": "https://urosario.edu.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://urosario.edu.co/rss.xml"],
    },
    "pereiracomovamos": {
        "url": "https://www.pereiracomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.pereiracomovamos.org/es/rss.xml"],
    },
    "proantioquia": {
        "url": "https://proantioquia.org.co",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://proantioquia.org.co/feed/", "https://proantioquia.org.co/feed/"],
    },
    "probarranquilla": {
        "url": "https://probarranquilla.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://probarranquilla.org/feed/", "https://probarranquilla.org/feed/"],
    },
    "propacifico": {
        "url": "https://propacifico.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://propacifico.org/feed/", "https://propacifico.org/feed/"],
    },
    "redcomovamos": {
        "url": "https://redcomovamos.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://redcomovamos.org/feed/", "https://redcomovamos.org/feed/"],
    },
    "redfamiliacolombia": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.redfamiliacolombia.org",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.redfamiliacolombia.org/inicio/feed/", "https://www.redfamiliacolombia.org/feed/"],
    },
    "teleamiga": {  # OJO: cuerpo corto en la muestra
        "url": "https://teleamiga.tv",
        "category": "opinion",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "alerta_red": {  # OJO: archivo pequeno
        "url": "https://www.alerta.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/quejodromo/", "/bochinches/", "/judiciales/", "/servicios/"],
        "rss_feeds": [],
    },
    "canalpyc": {
        "url": "https://canalpyc.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://canalpyc.com/comments/feed/", "https://canalpyc.com/feed/"],
    },
    "canaltrece": {
        "url": "https://canaltrece.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/noticias/"],
        "rss_feeds": ["https://canaltrece.com.co/feed/", "https://canaltrece.com.co/feed/"],
    },
    "canaltro": {
        "url": "https://canaltro.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://canaltro.com/feed/", "https://canaltro.com/feed/"],
    },
    "catatumbonoticias": {
        "url": "https://catatumbonoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/economia/", "/sucesos/", "/internacional/", "/politica/", "/regional/"],
        "rss_feeds": ["https://catatumbonoticias.com/feed/", "https://catatumbonoticias.com/feed/"],
    },
    "cundinamarcaenlinea": {
        "url": "https://www.cundinamarcaenlinea.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.cundinamarcaenlinea.com/feed/", "https://www.cundinamarcaenlinea.com/comments/feed/"],
    },
    "diariodelcesar": {
        "url": "https://www.diariodelcesar.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/archivos/"],
        "rss_feeds": ["https://www.diariodelcesar.com/feed/", "https://www.diariodelcesar.com/feed/"],
    },
    "ecosdelcombeima": {
        "url": "https://www.ecosdelcombeima.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/opinion/", "/tolima/", "/ibague/", "/politica/", "/economia/"],
        "rss_feeds": ["https://www.ecosdelcombeima.com/rss.xml"],
    },
    "eldiarioboyaca": {
        "url": "https://eldiarioboyaca.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://eldiarioboyaca.com/comments/feed/", "https://eldiarioboyaca.com/feed/"],
    },
    "eltabloide": {
        "url": "https://eltabloide.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://eltabloide.com.co/feed/", "https://eltabloide.com.co/feed/"],
    },
    "florencianoticias": {
        "url": "https://florencianoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://florencianoticias.com/feed/", "https://florencianoticias.com/feed/"],
    },
    "hora13": {  # OJO: cuerpo corto en la muestra
        "url": "https://h13n.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/", "/wp-json/"],
        "rss_feeds": ["https://h13n.com/feed/", "https://h13n.com/feed/"],
    },
    "hsbnoticias": {
        "url": "https://www.hsbnoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.hsbnoticias.com/feed/", "https://www.hsbnoticias.com/feed/"],
    },
    "informativodelguaico": {  # OJO: cuerpo corto en la muestra
        "url": "https://informativodelguaico.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://informativodelguaico.com/comments/feed/", "https://informativodelguaico.com/feed/"],
    },
    "marchadigital": {
        "url": "https://marchadigital.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/category/", "/03/"],
        "rss_feeds": [],
    },
    "meridianoregional": {  # OJO: cuerpo corto en la muestra
        "url": "https://meridianoregional.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/"],
        "rss_feeds": ["https://meridianoregional.com/feed/", "https://meridianoregional.com/feed/"],
    },
    "metropolitano": {
        "url": "https://metropolitano.com.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://metropolitano.com.co/comments/feed/", "https://metropolitano.com.co/feed/"],
    },
    "narinoahora": {
        "url": "https://narinoahora.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/", "/page/"],
        "rss_feeds": ["https://narinoahora.com/comments/feed/", "https://narinoahora.com/feed/"],
    },
    "noscogiolanoche": {
        "url": "https://noscogiolanoche.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://noscogiolanoche.com/comments/feed/", "https://noscogiolanoche.com/feed/"],
    },
    "noticierodelllano": {
        "url": "https://www.noticierodelllano.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.blogger.com/feeds/8074909602984415733/posts/default", "https://www.noticierodelllano.com/feeds/posts/default?alt=rss"],
    },
    "notimovilchoco": {  # OJO: cuerpo corto en la muestra
        "url": "https://notimovilchoco.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://notimovilchoco.com/feed/", "https://notimovilchoco.com/feed/"],
    },
    "ondasdelmeta": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.ondasdelmeta.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/", "/category/"],
        "rss_feeds": ["https://www.ondasdelmeta.com/feed/", "https://www.ondasdelmeta.com/feed/"],
    },
    "opinioncaribe": {  # OJO: cuerpo corto en la muestra
        "url": "https://www.opinioncaribe.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.opinioncaribe.com/feed/", "https://www.opinioncaribe.com/feed/"],
    },
    "proclamadelpacifico": {
        "url": "https://proclamadelpacifico.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://proclamadelpacifico.com/comments/feed/", "https://proclamadelpacifico.com/feed/"],
    },
    "qradiochoco": {  # OJO: cuerpo corto en la muestra
        "url": "https://qradiochoco.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://qradiochoco.com/comments/feed/", "https://qradiochoco.com/feed/"],
    },
    "radio1040am": {
        "url": "https://radio1040am.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://radio1040am.com/comments/feed/", "https://radio1040am.com/feed/"],
    },
    "sucrehoy": {
        "url": "https://sucrehoy.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/tag/"],
        "rss_feeds": ["https://sucrehoy.com/feed/", "https://sucrehoy.com/feed/"],
    },
    "telecafe": {  # OJO: cuerpo corto en la muestra
        "url": "https://telecafe.gov.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/", "/wp-json/", "/transparencia/", "/cdn-cgi/"],
        "rss_feeds": ["https://telecafe.gov.co/comments/feed/", "https://telecafe.gov.co/feed/"],
    },
    "teleislas": {  # OJO: cuerpo corto en la muestra
        "url": "https://teleislas.gov.co",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/wp-content/", "/wp-includes/"],
        "rss_feeds": ["https://teleislas.gov.co/feed/", "https://teleislas.gov.co/feed/"],
    },
    "telepetroleo": {
        "url": "https://telepetroleo.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/comunidad/", "/seguridad/", "/politica/"],
        "rss_feeds": ["https://telepetroleo.com/comments/feed/", "https://telepetroleo.com/feed/"],
    },
    "ultimahoraboy": {
        "url": "https://ultimahoraboy.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": ["/boyaca/", "/tunja/"],
        "rss_feeds": ["https://ultimahoraboy.com/feed/", "https://ultimahoraboy.com/feed/"],
    },
    "urabanoticias": {  # OJO: archivo pequeno
        "url": "https://urabanoticias.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://urabanoticias.com/feed/", "https://urabanoticias.com/feed/"],
    },
    "viveelmeta": {
        "url": "https://www.viveelmeta.com",
        "category": "regional",
        "mode": "sitemap",
        "url_filters": [],
        "rss_feeds": ["https://www.viveelmeta.com/feed/", "https://www.viveelmeta.com/feed/"],
    },

    # --- Asociaciones de gobiernos territoriales y ejecutivo local ---
    # El eje TERRITORIO vs CENTRO, que no tenia ninguna voz en el catalogo.
    # fcm y asocapitales republican comunicados de alcaldes, asi que colisionan
    # entre si y con las alcaldias: deduplicar por hash de contenido, no por URL.

    "asocapitales": {
        "url": "https://asocapitales.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": ["https://www.asocapitales.co/rss.xml"],
    },
    "fcm": {
        "url": "https://fcm.org.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "medellindistrito": {
        "url": "https://www.medellin.gov.co",
        "category": "institucional",
        "mode": "direct",
        "url_filters": [],
        "rss_feeds": [],
    },
    "primiciadiario": {  # OJO: cuerpo corto en la muestra
        "url": "https://primiciadiario.com",
        "category": "nacional",
        "mode": "sitemap",
        "url_filters": ["/archivo/"],
        "rss_feeds": ["https://primiciadiario.com/comments/feed/", "https://primiciadiario.com/feed/"],
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
