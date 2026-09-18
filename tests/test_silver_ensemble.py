"""Ensemble de jueces: consenso, calibración y el flujo completo sin LLM.

Nada aquí llama a una API. Los jueces son falsos y devuelven lo que el test
les dicta; lo que se prueba es la lógica que decide qué entra al silver y
con qué marca.
"""

import json
from pathlib import Path

import pytest

from src.agents.silver import calibration, consensus, ensemble
from src.agents.silver.judge import AXIS_NAMES, DOMINANT_KEY
from src.agents.silver.judges import OUTPUT_FORMAT_BLOCK, Verdict, system_prompt_from


def v(judge: str, dominant: str | None, ok: bool = True, family: str | None = None,
      quota: bool = False) -> Verdict:
    return Verdict(judge=judge, model=f"{judge}-model", family=family or judge,
                   dominant=dominant, ok=ok, quota=quota,
                   scores={a: (0.9 if a == dominant else 0.1) for a in AXIS_NAMES}
                   if ok else {})


# ---------------------------------------------------------------- consenso --

def test_unanime_se_acepta_con_cualquier_regla():
    verdicts = [v("gemini", "populismo"), v("claude", "populismo")]
    for rule in consensus.RULES:
        c = consensus.resolve(verdicts, rule)
        assert (c.label, c.status, c.accepted) == ("populismo", consensus.UNANIME, True)
        assert c.agreement == 1.0


def test_mayoria_depende_de_la_regla():
    verdicts = [v("a", "populismo"), v("b", "populismo"), v("c", "progresismo")]
    mayoria = consensus.resolve(verdicts, "majority")
    assert (mayoria.label, mayoria.status, mayoria.accepted) == \
        ("populismo", consensus.MAYORIA, True)
    assert mayoria.agreement == pytest.approx(2 / 3)

    estricta = consensus.resolve(verdicts, "unanimous")
    # La etiqueta se CONSERVA aunque no se acepte: descartarla sesgaría el silver.
    assert estricta.label == "populismo"
    assert estricta.accepted is False


def test_empate_no_finge_una_mayoritaria():
    verdicts = [v("gemini", "populismo"), v("claude", "progresismo")]
    c = consensus.resolve(verdicts)
    assert c.status == consensus.DISCREPANCIA
    assert c.label is None and c.agreement == 0.0 and c.accepted is False
    assert c.votes == {"populismo": 1, "progresismo": 1}


def test_pluralidad_sin_mayoria_es_discrepancia_pero_conserva_etiqueta():
    verdicts = [v("a", "populismo"), v("b", "progresismo"), v("c", "soberanismo"),
                v("d", "populismo")]
    c = consensus.resolve(verdicts)          # 2 de 4 = 50 %, no es mayoría
    assert c.status == consensus.DISCREPANCIA
    assert c.label == "populismo" and c.accepted is False
    assert c.agreement == pytest.approx(0.5)


def test_un_solo_juez_valido_nunca_es_consenso():
    # El otro juez falló: no hay con quién comparar. Se conserva la etiqueta,
    # marcada como UNICO, para que quien entrena decida.
    verdicts = [v("gemini", "populismo"), v("claude", None, ok=False)]
    c = consensus.resolve(verdicts)
    assert (c.label, c.status, c.accepted) == ("populismo", consensus.UNICO, False)
    assert (c.n_judges, c.n_valid) == (2, 1)


def test_sin_ningun_veredicto():
    c = consensus.resolve([v("a", None, ok=False), v("b", None, ok=False)])
    assert (c.label, c.status, c.n_valid) == (None, consensus.SIN_VEREDICTO, 0)


def test_regla_desconocida_falla_ruidosamente():
    with pytest.raises(ValueError):
        consensus.resolve([v("a", "populismo")], "plurality")


def test_scores_son_la_media_de_los_jueces_validos():
    verdicts = [v("a", "populismo"), v("b", "progresismo"), v("c", None, ok=False)]
    m = consensus.mean_scores(verdicts)
    assert m["populismo"] == pytest.approx(0.5)      # (0.9 + 0.1) / 2
    assert m["progresismo"] == pytest.approx(0.5)
    assert m["soberanismo"] == pytest.approx(0.1)


# ---------------------------------------------------------------- codebook --

def test_codebook_externo_recibe_el_bloque_de_formato(tmp_path):
    """El codebook del anotador está escrito para humanos: no dice nada de
    scores en [0, 1] ni de "dominant". Sin el bloque, el juez no sabe qué
    devolver aunque el esquema le fuerce la estructura."""
    cb = tmp_path / "codebook.md"
    cb.write_text("# Codebook\n\nPopulismo es...", encoding="utf-8")
    prompt = system_prompt_from(cb)
    assert prompt.startswith("# Codebook")
    assert f'"{DOMINANT_KEY}"' in prompt
    for axis in AXIS_NAMES:
        assert f'"{axis}"' in prompt


def test_codebook_que_ya_trae_formato_no_se_duplica(tmp_path):
    cb = tmp_path / "codebook.md"
    cb.write_text('Reglas...\n{"dominant": "populismo"}', encoding="utf-8")
    assert OUTPUT_FORMAT_BLOCK not in system_prompt_from(cb)


def test_codebook_vacio_falla(tmp_path):
    cb = tmp_path / "vacio.md"
    cb.write_text("   \n", encoding="utf-8")
    with pytest.raises(ValueError):
        system_prompt_from(cb)


# ---------------------------------------------------------------- ensemble --

class FakeJudge:
    """Juez guionizado: devuelve por id lo que le diga el test."""

    def __init__(self, name: str, script: dict[str, str | None], family: str | None = None,
                 quota_on: set[str] | None = None):
        self.name = name
        self.model = f"{name}-model"
        self.family = family or name
        self.script = script
        self.quota_on = quota_on or set()
        self.seen: list[str] = []

    def judge(self, title, text):
        aid = title  # el test pone el id en el título para localizarlo
        self.seen.append(aid)
        if aid in self.quota_on:
            return Verdict(self.name, self.model, self.family, ok=False,
                           error="cuota", quota=True)
        label = self.script.get(aid)
        return v(self.name, label, ok=label is not None, family=self.family)


def _corpus(tmp_path: Path, ids: list[str]) -> Path:
    p = tmp_path / "articles.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for aid in ids:
            f.write(json.dumps({"id": aid, "title": aid, "text": "cuerpo " * 30,
                                "source": "s", "category": "c"}) + "\n")
    return p


def _leer(p: Path) -> list[dict]:
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_flujo_completo_escribe_silver_y_veredictos(tmp_path):
    ids = ["a", "b", "c", "d"]
    gemini = FakeJudge("gemini", {"a": "populismo", "b": "populismo", "c": "soberanismo",
                                  "d": "progresismo"})
    claude = FakeJudge("claude", {"a": "populismo", "b": "progresismo", "c": "soberanismo",
                                  "d": None})
    out = tmp_path / "silver.jsonl"

    summary = ensemble.label_with_ensemble(
        [gemini, claude], input_path=_corpus(tmp_path, ids), output_path=out,
        rule="majority", force=True, progress=False)

    silver = {r["id"]: r for r in _leer(out)}
    verdicts = {r["id"]: r for r in _leer(ensemble.verdicts_path_for(out))}

    # a: unánime; c: unánime; b: empate (sin etiqueta → no entra al silver);
    # d: solo gemini (UNICO → entra, no aceptado)
    assert set(silver) == {"a", "c", "d"}
    assert set(verdicts) == {"a", "b", "c", "d"}, "los veredictos se guardan TODOS"
    assert silver["a"]["consensus"]["status"] == consensus.UNANIME
    assert silver["a"]["label_source"] == ensemble.LABEL_SOURCE
    assert silver["a"]["label_idx"] is not None
    assert silver["d"]["consensus"]["status"] == consensus.UNICO
    assert silver["d"]["consensus"]["accepted"] is False
    assert verdicts["b"]["consensus"]["status"] == consensus.DISCREPANCIA
    assert summary["labeled"] == 3 and summary["accepted"] == 2
    assert summary["status"] == {consensus.UNANIME: 2, consensus.DISCREPANCIA: 1,
                                 consensus.UNICO: 1}


def test_el_gold_queda_fuera_y_el_cursor_avanza(tmp_path):
    ids = ["g1", "n1", "g2", "n2"]
    juez = FakeJudge("gemini", dict.fromkeys(ids, "populismo"))
    out = tmp_path / "silver.jsonl"

    ensemble.label_with_ensemble([juez], input_path=_corpus(tmp_path, ids),
                                 output_path=out, exclude_ids={"g1", "g2"},
                                 force=True, progress=False)

    assert juez.seen == ["n1", "n2"], "al gold no se le pregunta nada"
    assert {r["id"] for r in _leer(out)} == {"n1", "n2"}
    assert ensemble.read_cursor(out) == len(ids), "los excluidos no quedan pendientes"


def test_es_reanudable(tmp_path):
    ids = ["a", "b", "c"]
    juez = FakeJudge("gemini", dict.fromkeys(ids, "populismo"))
    corpus = _corpus(tmp_path, ids)
    out = tmp_path / "silver.jsonl"

    ensemble.label_with_ensemble([juez], input_path=corpus, output_path=out,
                                 max_articles=2, force=True, progress=False)
    assert ensemble.read_cursor(out) == 2
    ensemble.label_with_ensemble([juez], input_path=corpus, output_path=out,
                                 progress=False)
    assert [r["id"] for r in _leer(out)] == ["a", "b", "c"]
    assert juez.seen == ["a", "b", "c"], "no se repite ninguno"


def test_un_juez_sin_cuota_se_retira_y_los_demas_siguen(tmp_path):
    ids = ["a", "b", "c"]
    gemini = FakeJudge("gemini", dict.fromkeys(ids, "populismo"))
    claude = FakeJudge("claude", dict.fromkeys(ids, "populismo"), quota_on={"a"})
    out = tmp_path / "silver.jsonl"

    summary = ensemble.label_with_ensemble(
        [gemini, claude], input_path=_corpus(tmp_path, ids), output_path=out,
        force=True, progress=False)

    assert summary["retired_judges"] == ["claude"]
    assert claude.seen == ["a"], "tras la cuota no se le vuelve a preguntar"
    silver = {r["id"]: r for r in _leer(out)}
    # b y c los decidió gemini solo → UNICO, conservados pero no aceptados
    assert silver["b"]["consensus"]["status"] == consensus.UNICO
    assert silver["b"]["consensus"]["n_judges"] == 1


def test_si_ningun_juez_tiene_cuota_para_sin_avanzar(tmp_path):
    ids = ["a", "b"]
    juez = FakeJudge("gemini", {}, quota_on={"a", "b"})
    out = tmp_path / "silver.jsonl"

    summary = ensemble.label_with_ensemble([juez], input_path=_corpus(tmp_path, ids),
                                           output_path=out, force=True, progress=False)
    assert summary["cursor"] == 0, "el artículo se reintenta en la próxima corrida"
    assert not out.exists() or _leer(out) == []


def test_no_appendea_sobre_salida_sin_cursor(tmp_path):
    out = tmp_path / "silver.jsonl"
    out.write_text('{"id": "x"}\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        ensemble.label_with_ensemble([FakeJudge("g", {})],
                                     input_path=_corpus(tmp_path, ["a"]),
                                     output_path=out, progress=False)


# ------------------------------------------------------------- calibración --

def _rec(aid: str, votes: dict[str, str | None]) -> dict:
    return {"id": aid, "rule": "majority",
            "verdicts": [v(j, d, ok=d is not None).to_dict() for j, d in votes.items()]}


def test_calibracion_mide_si_el_acuerdo_predice_el_acierto():
    gold = {"1": "populismo", "2": "populismo", "3": "progresismo", "4": "soberanismo",
            "5": "populismo"}
    records = [
        _rec("1", {"gemini": "populismo", "claude": "populismo"}),     # unánime, acierta
        _rec("2", {"gemini": "populismo", "claude": "populismo"}),     # unánime, acierta
        _rec("3", {"gemini": "progresismo", "claude": "populismo"}),   # empate
        _rec("4", {"gemini": "globalismo", "claude": "globalismo"}),   # unánime, FALLA
        _rec("5", {"gemini": "populismo", "claude": None}),            # único
        _rec("fuera", {"gemini": "populismo", "claude": "populismo"}),  # no está en el gold
    ]
    r = calibration.calibrate(records, gold, rule="majority")

    assert r["n"] == 5, "solo cuentan los artículos con etiqueta humana"
    assert r["per_judge"]["gemini"]["accuracy"] == pytest.approx(4 / 5)
    assert r["per_judge"]["claude"]["ok"] == 4
    assert r["per_judge"]["claude"]["accuracy"] == pytest.approx(2 / 4)
    assert r["by_status"]["unanime"]["n"] == 3
    assert r["by_status"]["unanime"]["accuracy"] == pytest.approx(2 / 3)
    assert r["accepted"]["n"] == 3 and r["rejected"]["n"] == 2
    assert r["pairwise"]["claude|gemini"]["n"] == 4
    assert r["confusion_accepted"] == {"soberanismo→globalismo": 1}


def test_el_report_se_puede_recalcular_con_otra_regla_sin_llm():
    gold = {"1": "populismo"}
    records = [_rec("1", {"a": "populismo", "b": "populismo", "c": "progresismo"})]
    assert calibration.calibrate(records, gold, "majority")["accepted"]["n"] == 1
    assert calibration.calibrate(records, gold, "unanimous")["accepted"]["n"] == 0


def test_render_report_con_y_sin_datos():
    assert "Sin artículos" in calibration.render_report({"n": 0})
    gold = {"1": "populismo"}
    r = calibration.calibrate([_rec("1", {"gemini": "populismo", "claude": "populismo"})], gold)
    md = calibration.render_report(r)
    assert "Cada juez frente al humano" in md and "predice el acierto" in md
    assert "100.0 %" in md
