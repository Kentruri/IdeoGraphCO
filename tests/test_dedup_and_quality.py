"""Tests de deduplicación entre corridas y de la compuerta de calidad.

Valida el requisito operativo: correr el scraper dos veces NO debe traer
las mismas noticias — ni con la BD de dedup viva (caso normal), ni con la
BD perdida (guardia por ID contra el archivo de salida).
"""

import json

import pytest

import src.scraper.pipeline as pipeline_mod
from src.scraper.db import (
    compute_content_hash,
    is_already_scraped,
    is_duplicate_content,
    mark_as_scraped,
)
from src.scraper.quality import assess_article_quality

POLITICAL_TEXT = (
    "El Congreso de la República aprobó en segundo debate la reforma al sistema "
    "de salud, tras una sesión que se extendió por más de nueve horas. "
    "La ponencia mayoritaria defendió el nuevo esquema de aseguramiento público. "
    "\n\n"
    "El ministro del ramo celebró la votación y anunció que el Gobierno radicará "
    "los decretos reglamentarios antes de finalizar la legislatura en curso. "
    "La oposición, por su parte, anunció demandas ante la Corte Constitucional. "
    "\n\n"
    "Analistas consultados señalaron que el trámite aún debe superar la "
    "conciliación entre las cámaras, donde el Gobierno no tiene mayorías claras. "
    "El debate continuará la próxima semana con la discusión del articulado."
) * 3


# ---------------------------------------------------------------------------
# db.py — dedup persistente
# ---------------------------------------------------------------------------


def test_db_dedup_roundtrip(tmp_path):
    db = tmp_path / "history.db"
    url = "https://ejemplo.co/nota-1"
    content_hash = compute_content_hash("texto de la nota")

    assert not is_already_scraped(url, db_path=db)
    assert not is_duplicate_content(content_hash, db_path=db)

    mark_as_scraped(url, content_hash, "fuente", "nacional", "2026-08-07", db_path=db)

    assert is_already_scraped(url, db_path=db)
    assert is_duplicate_content(content_hash, db_path=db)
    # Otra URL con el MISMO contenido (cable republicado) → dup por hash
    assert not is_already_scraped("https://otro.co/republicada", db_path=db)
    assert is_duplicate_content(content_hash, db_path=db)


# ---------------------------------------------------------------------------
# Pipeline end-to-end: dos corridas no duplican
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_env(monkeypatch, tmp_path):
    """Pipeline con red y BD simuladas: N URLs descubiertas, extracción fake."""
    store = {"urls": set(), "hashes": set()}

    def fake_is_scraped(url):
        return url in store["urls"]

    def fake_is_dup_content(content_hash):
        return content_hash in store["hashes"]

    def fake_mark(url, content_hash, *args, **kwargs):
        store["urls"].add(url)
        store["hashes"].add(content_hash)

    def fake_discover(name, conf, max_articles, extra=None):
        return [f"https://ejemplo.co/{name}/nota-{i}" for i in range(5)]

    def fake_extract(url, source, category):
        text = POLITICAL_TEXT + f"\n\nIdentificador único: {url}."
        return {
            "id": url.rsplit("-", 1)[-1] + "-" + source,
            "url": url,
            "text": text,
            "title": "El Congreso aprueba la reforma en segundo debate",
            "authors": [],
            "source": source,
            "category": category,
            "date": "2026-08-07",
            "scraped_at": "2026-08-07T12:00:00+00:00",
            "content_hash": compute_content_hash(text),
        }

    monkeypatch.setattr(pipeline_mod, "is_already_scraped", fake_is_scraped)
    monkeypatch.setattr(pipeline_mod, "is_duplicate_content", fake_is_dup_content)
    monkeypatch.setattr(pipeline_mod, "mark_as_scraped", fake_mark)
    monkeypatch.setattr(pipeline_mod, "discover_candidate_urls", fake_discover)
    monkeypatch.setattr(pipeline_mod, "extract_article", fake_extract)
    monkeypatch.setattr(pipeline_mod, "is_url_allowed", lambda url: True)
    monkeypatch.setattr(pipeline_mod, "_adaptive_sleep", lambda n: None)

    output = tmp_path / "articles.jsonl"
    sources = {"fuentetest": {"url": "https://ejemplo.co", "category": "nacional", "mode": "direct"}}
    return store, output, sources


def _run_pipeline(output, sources):
    return pipeline_mod.scrape_pipeline(
        sources=sources,
        output_path=output,
        max_per_source=10,
        use_llm_filter=False,
    )


def test_second_run_brings_nothing_new(fake_env):
    store, output, sources = fake_env

    first = _run_pipeline(output, sources)
    assert first.get("kept", 0) == 5

    second = _run_pipeline(output, sources)
    assert second.get("kept", 0) == 0
    assert second.get("dup", 0) == 5  # todas ya en la BD de dedup

    lines = [json.loads(line) for line in open(output) if line.strip()]
    assert len(lines) == 5
    assert len({r["id"] for r in lines}) == 5


def test_output_guard_survives_lost_db(fake_env):
    """Si la BD de dedup se pierde, el archivo de salida NO se duplica."""
    store, output, sources = fake_env

    first = _run_pipeline(output, sources)
    assert first.get("kept", 0) == 5

    # Simular pérdida de scraper_history.db
    store["urls"].clear()
    store["hashes"].clear()

    second = _run_pipeline(output, sources)
    assert second.get("kept", 0) == 0
    assert second.get("dup_output", 0) == 5  # atrapadas por la guardia de salida

    lines = [json.loads(line) for line in open(output) if line.strip()]
    assert len(lines) == 5  # sin duplicados en el JSONL


# ---------------------------------------------------------------------------
# Compuerta de calidad
# ---------------------------------------------------------------------------


def test_quality_accepts_real_article():
    verdict = assess_article_quality(
        "El Congreso aprueba la reforma en segundo debate", POLITICAL_TEXT,
    )
    assert verdict.ok, verdict.reasons


def test_quality_accepts_two_paragraph_brief():
    """Un brief legítimo de 2 párrafos bien redactados pasa (caso El Nuevo Siglo)."""
    brief = (
        "De acuerdo con el texto de la solicitud, el Ejecutivo fundamenta su "
        "petición en la observación de un fenómeno de inasistencia en las "
        "comisiones constitucionales permanentes y en las sesiones plenarias.\n\n"
        "Según el ministro, esta situación genera demoras en la discusión de "
        "proyectos de ley definidos como prioritarios por el Gobierno nacional "
        "y afecta el cumplimiento de la agenda legislativa del semestre."
    )
    verdict = assess_article_quality("Gobierno endurece postura frente a inasistencias", brief)
    assert verdict.ok, verdict.reasons


def test_quality_rejects_listing_title():
    verdict = assess_article_quality(
        "Política: Últimas noticias, fotos, videos y artículos", POLITICAL_TEXT,
    )
    assert not verdict.ok
    assert "titulo_de_listado" in verdict.reasons


def test_quality_rejects_listing_structure():
    listing = "\n".join(f"Titular corto número {i}" for i in range(30))
    verdict = assess_article_quality("Sección", listing)
    assert not verdict.ok
    assert "estructura_de_listado" in verdict.reasons or "pocos_parrafos" in verdict.reasons


def test_quality_short_title_is_warning_not_rejection():
    verdict = assess_article_quality("ANDI", POLITICAL_TEXT)
    assert verdict.ok
    assert "sin_titulo" in verdict.warnings


def test_cleaner_new_rules():
    from src.scraper.cleaner import clean_article_text

    dirty = (
        POLITICAL_TEXT
        + "\nSiga a EL PAÍS en Google Discover y no se pierda las últimas noticias"
        + "\nEscucha este artículo\nAudio generado con IA de Google"
        + "\nTemas recomendados:\nNoticias Destacadas"
        + "\n* Pulzo.com se escribe con Z"
        + "\nVer el trino: pic.twitter.com/oEuAb5UPiU"
        + "\nEscriba a denuncias@medio.com para más información."
    )
    cleaned = clean_article_text(dirty)
    for garbage in (
        "Google Discover", "Escucha este artículo", "generado con IA",
        "Temas recomendados", "Noticias Destacadas", "se escribe con Z",
        "pic.twitter.com", "@medio.com",
    ):
        assert garbage not in cleaned, garbage
    assert "Congreso" in cleaned


def test_cleaner_template_artifacts():
    """Artefactos de plantilla medidos en el corpus real (auditoría ago-2026).

    Los 6 patrones que sobrevivían al cleaner: reproductor de audio, etiqueta
    de sección suelta, "Compartir:" (el ':' rompía el ancla), firma
    institucional, CTAs que abren con emoji y separadores tipográficos.
    """
    from src.scraper.cleaner import clean_article_text

    dirty = (
        POLITICAL_TEXT
        + "\nCompartir:"
        + "\n0:00\n/"
        + "\nPolítica"
        + "\nMinisterio del Interior"
        + "\n***"
        + "\n↩︎ -"
        + "\nExclusivo suscriptores"
        + "\n👉 Lea más sobre el Congreso y otras noticias del mundo político."
        + "\n✉️ Si tiene interés en más temas políticos escríbanos al correo."
    )
    cleaned = clean_article_text(dirty)
    for garbage in (
        "Compartir:", "0:00", "Ministerio del Interior", "***", "↩︎",
        "Exclusivo suscriptores", "👉", "✉️",
    ):
        assert garbage not in cleaned, garbage
    assert "Congreso" in cleaned


def test_cleaner_preserves_legitimate_content():
    """Los patrones nuevos NO deben tocar contenido editorial legítimo."""
    from src.scraper.cleaner import clean_article_text

    # Nota editorial con asterisco (no es separador)
    nota = "* El nombre de las mujeres gestantes fue cambiado para proteger su identidad."
    assert "mujeres gestantes" in clean_article_text(nota)

    # Crédito de financiación (verificado en el corpus de volcanicas)
    credito = "*** Este proyecto se realizó con el apoyo de JournalismFund Europe."
    assert "JournalismFund" in clean_article_text(credito)

    # "Ministerio" dentro de una oración real, no como firma suelta
    prosa = (
        "El Ministerio del Interior radicó el proyecto de ley ante el Congreso "
        "de la República en la sesión de ayer."
    )
    assert "radicó el proyecto" in clean_article_text(prosa)

    # Emoji dentro de una cita: es contenido, no CTA
    cita = "El senador escribió: 🔴 Rechazo total a la reforma tributaria del Gobierno."
    assert "Rechazo total" in clean_article_text(cita)

    # Hora dentro de una oración (no es el cronómetro del reproductor)
    hora = "La plenaria se instaló a las 10:30 de la mañana con quórum decisorio."
    assert "quórum decisorio" in clean_article_text(hora)


def test_filter_blocking_text_issues():
    """Los issues bloqueantes descartan aunque la categoría sea política."""
    from src.scraper.article_filter import BLOCKING_TEXT_ISSUES, TEXT_ISSUES

    assert "boilerplate_residual" in TEXT_ISSUES
    # El boilerplate es solo señal para mejorar el cleaner: NO descarta.
    assert "boilerplate_residual" not in BLOCKING_TEXT_ISSUES
    # Un digest rompe el supuesto single-label del proyecto: sí descarta.
    assert "digest_multinoticia" in BLOCKING_TEXT_ISSUES
    assert BLOCKING_TEXT_ISSUES <= set(TEXT_ISSUES)


def test_cleaner_related_articles_carousel():
    """Carrusel de notas relacionadas (contextoganadero, ago-2026).

    El artículo llegaba con el titular y la firma de OTRA nota al inicio,
    "Cargando...", el lede duplicado, y 12 líneas de firmas de relacionadas
    al final: 26 líneas de las que solo 10 eran cuerpo.
    """
    from src.scraper.cleaner import clean_article_text

    cuerpo = (
        "De acuerdo con el Dane, la exportación de carne creció en enero. "
        "El informe de Comercio Exterior detalla las cifras del sector."
    )
    dirty = (
        "Una nueva era en trazabilidad: Sinigán V6 entra en operación\n"
        "PorPedro Fonseca-16 de Abril 2026\n"
        "Cargando...\n"
        "Por - 04 de Marzo 2014\n"
        f"{cuerpo}\n"
        f"{cuerpo}\n"                       # lede duplicado por el CMS
        "Noticias Relacionadas\n"
        "PorMelanny Orozco-26 de Marzo 2026\n"
        "PorAngie Barbosa-25 de Marzo 2026\n"
    )
    cleaned = clean_article_text(dirty, source_name="contextoganadero")

    assert cleaned.startswith("De acuerdo con el Dane")   # arranca en el cuerpo
    assert "Sinigán V6" not in cleaned                    # titular de otra nota
    assert "Cargando" not in cleaned
    assert "Noticias Relacionadas" not in cleaned
    assert "Melanny Orozco" not in cleaned
    assert cleaned.count("De acuerdo con el Dane") == 1   # lede desduplicado


def test_cleaner_subscription_footer_block():
    """Bloque de suscripción/comentarios al cierre (ambitojuridico)."""
    from src.scraper.cleaner import clean_article_text

    dirty = (
        "El Ministerio del Trabajo expidió el Decreto 992 de 2026, que reglamenta "
        "las medidas contra el acoso laboral en las entidades públicas.\n"
        "Gracias por leernos. Si le gusta estar informado, suscríbase.\n"
        "¡Bienvenido a nuestra sección de comentarios!\n"
        "Para unirte a la conversación, necesitas estar suscrito.\n"
        "Siga nuestro nuevo canal de WhatsApp.\n"
    )
    cleaned = clean_article_text(dirty, source_name="ambitojuridico")

    assert "Decreto 992" in cleaned
    for junk in ("Gracias por leernos", "sección de comentarios",
                 "estar suscrito", "WhatsApp"):
        assert junk not in cleaned, junk


def test_cleaner_keeps_prose_starting_with_por():
    """'Por otra parte' / 'Por eso' son prosa, no firmas."""
    from src.scraper.cleaner import clean_article_text

    for prosa in (
        "Por otra parte, la reglamentación establece que los empleadores deberán "
        "adoptar protocolos de prevención del acoso laboral.",
        "Por eso el Congreso aplazó el debate hasta la próxima legislatura.",
        "El decreto se firmó el 16 de abril de 2026 según la Presidencia.",
    ):
        assert clean_article_text(prosa).strip() == prosa, prosa[:40]
