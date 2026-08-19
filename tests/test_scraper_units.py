"""Tests de las mejoras del scraper: URLs, news-sitemap, GDELT, prefilter."""

from src.scraper.gdelt import map_candidates_to_sources, parse_artlist
from src.scraper.parser import parse_news_sitemap_xml
from src.scraper.urls import dedupe_normalized, domain_of, normalize_url


def test_normalize_url_strips_tracking():
    url = "https://www.eltiempo.com/politica/nota-1?utm_source=tw&utm_medium=x&id=5#seccion"
    assert normalize_url(url) == "https://www.eltiempo.com/politica/nota-1?id=5"


def test_normalize_url_trailing_slash_and_case():
    assert normalize_url("HTTPS://WWW.Semana.com/nacion/nota/") == (
        "https://www.semana.com/nacion/nota"
    )
    # La raíz conserva su slash
    assert normalize_url("https://ejemplo.co/") == "https://ejemplo.co/"


def test_dedupe_normalized_preserves_order():
    urls = [
        "https://a.co/x?utm_source=1",
        "https://a.co/x",
        "https://a.co/y",
    ]
    assert dedupe_normalized(urls) == ["https://a.co/x", "https://a.co/y"]


def test_domain_of():
    assert domain_of("https://www.elespectador.com/politica/n") == "elespectador.com"


def test_parse_news_sitemap_lastmod_and_news_date():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
      <url>
        <loc>https://m.co/vieja</loc>
        <lastmod>2026-08-01T10:00:00Z</lastmod>
      </url>
      <url>
        <loc>https://m.co/nueva</loc>
        <news:news><news:publication_date>2026-08-04T09:00:00Z</news:publication_date></news:news>
      </url>
    </urlset>"""
    entries = dict(parse_news_sitemap_xml(xml))
    assert entries["https://m.co/vieja"].startswith("2026-08-01")
    assert entries["https://m.co/nueva"].startswith("2026-08-04")


def test_gdelt_parse_and_mapping():
    payload = {
        "articles": [
            {"url": "https://www.eltiempo.com/politica/n1?utm_source=gdelt",
             "title": "n1", "seendate": "20260804T120000Z"},
            {"url": "https://medio-desconocido.co/nota", "title": "n2",
             "seendate": "20260804T110000Z"},
        ]
    }
    candidates = parse_artlist(payload)
    assert candidates[0]["url"] == "https://www.eltiempo.com/politica/n1"
    assert candidates[0]["domain"] == "eltiempo.com"

    sources = {"eltiempo": {"url": "https://www.eltiempo.com"}}
    mapped = map_candidates_to_sources(candidates, sources)
    assert mapped == {"eltiempo": ["https://www.eltiempo.com/politica/n1"]}


def test_prefilter_train_and_decide(tmp_path):
    """Entrena un prefilter sintético y verifica la cascada drop/keep/uncertain."""
    import json
    import subprocess
    import sys

    log = tmp_path / "decisions.jsonl"
    with open(log, "w") as f:
        for i in range(150):
            f.write(json.dumps({
                "id": f"pol{i}", "engine": "llm", "kept": True,
                "text_head": ("El congreso debatió la reforma política del gobierno "
                              "y la corte constitucional revisó la ley. " * 6) + str(i),
            }) + "\n")
            f.write(json.dumps({
                "id": f"dep{i}", "engine": "llm", "kept": False,
                "text_head": ("El equipo de fútbol ganó el partido del torneo con goles "
                              "del delantero en el estadio local. " * 6) + str(i),
            }) + "\n")

    bundle = tmp_path / "prefilter.joblib"
    result = subprocess.run(
        [sys.executable, "scripts/train_prefilter.py",
         "--log", str(log), "--output", str(bundle), "--min-samples", "100"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert bundle.exists()

    from src.scraper.prefilter import PoliticalPrefilter

    prefilter = PoliticalPrefilter.load(bundle)
    assert prefilter.decide(
        "La reforma política fue aprobada por el congreso y revisada por la corte "
        "constitucional del gobierno nacional en el debate legislativo." * 3
    ).action == "keep"
    assert prefilter.decide(
        "El delantero anotó tres goles en el partido del torneo de fútbol y el "
        "equipo celebró en el estadio con la afición local." * 3
    ).action == "drop"
