"""Integración con Label Studio: plantilla, tareas y parseo del export.

El contrato crítico: `parse_export()` debe devolver EXACTAMENTE el formato de
`read_book()` de scripts/ingest_gold.py, porque el α de Krippendorff y el
flujo de consenso se calculan aguas abajo sin distinguir la herramienta.
"""

import json
import xml.etree.ElementTree as ET

from src.agents.gold.labelstudio import (
    LABELING_CONFIG,
    build_labeling_config,
    build_tasks,
    parse_export,
)
from src.core.schema import IDEOLOGY_CLASSES


def test_default_config_asks_only_for_dominant_class():
    """Por defecto: UNA decisión por artículo (la clase), sin escalas 1-5.

    Las escalas eran un residuo del diseño de regresión sobre 8 ejes; el
    clasificador multiclase solo consume la dominante, y pedir 9 decisiones
    en vez de 1 multiplica el trabajo del anotador sin alimentar al modelo.
    """
    root = ET.fromstring(build_labeling_config())

    assert list(root.iter("Rating")) == [], "el default no debe pedir escalas"

    choices = [el for el in root.iter("Choices") if el.get("name") == "clase_dominante"]
    assert len(choices) == 1
    assert choices[0].get("required") == "true", "la dominante debe ser obligatoria"
    values = {c.get("value") for c in choices[0].iter("Choice")}
    assert values == set(IDEOLOGY_CLASSES)
    # cada botón lleva una pista legible del codebook
    assert all(c.get("hint") for c in choices[0].iter("Choice"))

    assert any(el.get("name") == "notes" for el in root.iter("TextArea"))
    assert LABELING_CONFIG == build_labeling_config()


def test_with_scales_adds_the_eight_axes():
    root = ET.fromstring(build_labeling_config(with_scales=True))

    ratings = {el.get("name") for el in root.iter("Rating")}
    assert ratings == set(IDEOLOGY_CLASSES)
    for el in root.iter("Rating"):
        assert el.get("maxRating") == "5"
    # la dominante sigue presente y obligatoria
    choices = [el for el in root.iter("Choices") if el.get("name") == "clase_dominante"]
    assert choices and choices[0].get("required") == "true"


def test_build_tasks_hides_source_and_category():
    """La anotación es ciega al medio: source/category/url no viajan a la UI."""
    articles = [{
        "id": "abc123", "title": "Título", "text": "Cuerpo del artículo.",
        "source": "semanariovoz", "category": "independiente",
        "url": "https://x.co/a", "date": "2026-01-01",
    }]
    (task,) = build_tasks(articles)
    assert task["data"]["id"] == "abc123"
    assert task["data"]["text"] == "Cuerpo del artículo."
    assert "source" not in task["data"]
    assert "category" not in task["data"]
    assert "url" not in task["data"]


def _ls_task(article_id, results, extra_annotations=None):
    annotations = [{"result": results}]
    if extra_annotations:
        annotations = extra_annotations + annotations
    return {
        "id": 1,
        "data": {"id": article_id, "title": "t", "text": "x"},
        "annotations": annotations,
    }


def _rating(axis, value):
    return {"from_name": axis, "to_name": "text", "type": "rating",
            "value": {"rating": value}}


def _dominant(cls):
    return {"from_name": "clase_dominante", "to_name": "text", "type": "choices",
            "value": {"choices": [cls]}}


def _notes(text):
    return {"from_name": "notes", "to_name": "text", "type": "textarea",
            "value": {"text": [text]}}


def test_parse_export_matches_read_book_contract(tmp_path):
    export = [
        _ls_task("art1", [
            _rating("populismo", 5), _rating("personalismo", 2),
            _dominant("populismo"), _notes("dudé con personalismo"),
        ]),
        # rating 0 = estrellas sin tocar → eje sin anotar (None)
        _ls_task("art2", [_rating("soberanismo", 0), _dominant("soberanismo")]),
        # clase inválida (no está en el codebook) → dominante None
        _ls_task("art3", [_dominant("otra_cosa")]),
    ]
    path = tmp_path / "export.json"
    path.write_text(json.dumps(export), encoding="utf-8")

    parsed = parse_export(path)

    assert set(parsed) == {"art1", "art2", "art3"}
    a1 = parsed["art1"]
    assert set(a1) == {"dominant", "scores", "notes"}          # contrato exacto
    assert a1["dominant"] == "populismo"
    assert a1["scores"]["populismo"] == 5
    assert a1["scores"]["personalismo"] == 2
    assert a1["scores"]["globalismo"] is None                   # eje sin anotar
    assert a1["notes"] == "dudé con personalismo"
    assert set(a1["scores"]) == set(IDEOLOGY_CLASSES)

    assert parsed["art2"]["scores"]["soberanismo"] is None      # 0 estrellas
    assert parsed["art2"]["dominant"] == "soberanismo"
    assert parsed["art3"]["dominant"] is None


def test_parse_export_uses_last_annotation_and_skips_cancelled(tmp_path):
    """Si el anotador guardó dos veces, vale la última; las canceladas no cuentan."""
    task = _ls_task(
        "art1",
        [_dominant("progresismo")],                              # decisión final
        extra_annotations=[
            {"result": [_dominant("populismo")]},                # primer intento
            {"was_cancelled": True, "result": [_dominant("garbage")]},
        ],
    )
    # la cancelada va al final para probar que se ignora aunque sea la última
    task["annotations"].append(
        {"was_cancelled": True, "result": [_dominant("conservadurismo")]}
    )
    path = tmp_path / "export.json"
    path.write_text(json.dumps([task]), encoding="utf-8")

    assert parse_export(path)["art1"]["dominant"] == "progresismo"
