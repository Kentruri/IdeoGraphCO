"""El gold no puede filtrarse al silver ni al entrenamiento.

Los 1.301 artículos del gold son el conjunto de PRUEBA del OE3. Si el juez
LLM les pone etiqueta silver, el modelo acaba evaluándose contra el juicio de
otro modelo en vez de contra el humano, y las métricas son circulares. Si
además acaban en train/val, el modelo se evalúa sobre lo que memorizó.

Ninguna de las dos cosas da error en tiempo de ejecución: producen números
buenos y falsos. De ahí estos tests.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.silver import judge
from src.agents.silver.judge import AXIS_NAMES, DOMINANT_KEY

ROOT = Path(__file__).resolve().parent.parent


def _articulo(aid: str) -> dict:
    return {"id": aid, "title": f"Titular {aid}",
            "text": "El Congreso debatió la reforma. " * 20,
            "source": "prueba", "category": "nacional"}


def _respuesta_valida(*_a, **_k) -> str:
    """Respuesta con el esquema que `parse_response` exige de verdad."""
    data = {axis: 0.1 for axis in AXIS_NAMES}
    data["populismo"] = 0.9
    data[DOMINANT_KEY] = "populismo"
    return json.dumps(data)


def _etiquetar(tmp_path, articulos, exclude_ids):
    entrada = tmp_path / "in.jsonl"
    entrada.write_text(
        "\n".join(json.dumps(a, ensure_ascii=False) for a in articulos) + "\n",
        encoding="utf-8")
    salida = tmp_path / "out.jsonl"
    llamadas = []

    def espia(*a, **k):
        llamadas.append(1)
        return _respuesta_valida()

    with patch.object(judge, "_call_gemini_with_retry", side_effect=espia), \
         patch.object(judge.time, "sleep", lambda s: None):
        judge.label_news_file(llm_client=None, input_path=entrada,
                              output_path=salida, force=True,
                              exclude_ids=exclude_ids)

    escritos = [json.loads(line) for line in
                salida.read_text(encoding="utf-8").splitlines() if line.strip()]
    return escritos, len(llamadas)


def test_el_gold_no_recibe_etiqueta_silver(tmp_path):
    gold = {"g1", "g2", "g3"}
    articulos = [_articulo(i) for i in ["g1", "n1", "g2", "n2", "g3"]]

    escritos, llamadas = _etiquetar(tmp_path, articulos, gold)

    assert {a["id"] for a in escritos} == {"n1", "n2"}
    assert not {a["id"] for a in escritos} & gold
    # Y tampoco se gastó una llamada al LLM en ellos.
    assert llamadas == 2


def test_sin_exclusiones_se_etiqueta_todo(tmp_path):
    # La guarda debe ser explícita: si nadie pasa exclude_ids, el juez etiqueta
    # todo. Es lo que hace que olvidarse del gold sea peligroso, y por eso
    # scripts/label.py lo carga por defecto (ver el test de abajo).
    articulos = [_articulo(i) for i in ["a", "b", "c"]]

    escritos, llamadas = _etiquetar(tmp_path, articulos, None)

    assert len(escritos) == 3 and llamadas == 3


def test_el_cursor_avanza_sobre_los_excluidos(tmp_path):
    """Un excluido no puede quedar como "pendiente para la próxima".

    Si el cursor no avanzara, cada corrida volvería a toparse con el mismo
    artículo del gold y el etiquetado no progresaría nunca.
    """
    gold = {"g1"}
    articulos = [_articulo(i) for i in ["g1", "n1"]]
    _etiquetar(tmp_path, articulos, gold)

    cursor = int((tmp_path / "out.jsonl.cursor").read_text().strip())
    assert cursor == len(articulos)


def test_label_py_excluye_el_gold_por_defecto():
    """Hay que pasar una bandera explícita para contaminar el test."""
    fuente = (ROOT / "scripts" / "label.py").read_text(encoding="utf-8")
    assert "gold_set_v2_ids.json" in fuente
    assert "exclude_ids=exclude_ids" in fuente
    assert "--allow-gold-in-silver" in fuente


def test_prepare_splits_prefiere_el_gold_vigente():
    """Regresión: el respaldo miraba solo gold_set_v1_ids.json.

    Con un gold v2 muestreado, el test se armaba con artículos que no eran
    los reservados y los 1.301 podían acabar en entrenamiento.
    """
    fuente = (ROOT / "scripts" / "prepare_splits.py").read_text(encoding="utf-8")
    i2 = fuente.index("gold_set_v2_ids.json")
    i1 = fuente.index("gold_set_v1_ids.json")
    assert i2 < i1, "el v2 debe consultarse antes que el v1"


@pytest.mark.skipif(not (ROOT / "annotation" / "gold_set_v2_ids.json").exists(),
                    reason="no hay gold muestreado")
def test_los_ids_del_gold_son_unicos_y_estan_completos():
    ids = json.loads((ROOT / "annotation" / "gold_set_v2_ids.json")
                     .read_text(encoding="utf-8"))
    ids = ids if isinstance(ids, list) else ids.get("ids", [])
    assert len(ids) == len(set(ids)), "hay IDs repetidos en el gold"

    tareas = json.loads((ROOT / "annotation" / "labelstudio" /
                         "gold_set_v2_juan_tasks.json").read_text(encoding="utf-8"))
    # Lo que se manda a anotar debe ser exactamente lo que se reserva.
    assert {t["data"]["id"] for t in tareas} == set(ids)
