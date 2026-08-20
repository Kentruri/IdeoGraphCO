"""Composición canónica del input: titular limpio + cuerpo.

Invariante crítica: el juez que asigna la etiqueta, el entrenamiento que la
aprende y la inferencia que la predice deben ver EL MISMO texto. Antes el
juez y el entrenamiento veían solo `text` y la API antependía el titular —
train/serve skew silencioso (auditoría ago-2026).
"""

import json
import tempfile
from pathlib import Path

from src.core.text import build_model_input, strip_outlet_suffix


class TestStripOutletSuffix:
    """Quitar el nombre del medio: es una cadena constante por fuente y
    dejarla convertiría el titular en una huella del medio."""

    def test_strips_real_outlet_suffixes(self):
        casos = [
            ("Exportación de carne creció | CONtexto Ganadero", "Exportación de carne creció"),
            ("Se evaluó Savia Salud - Concejo de Medellín", "Se evaluó Savia Salud"),
            ("Informe de conflicto armado - Indepaz", "Informe de conflicto armado"),
            ("Quedan 320 apartamentos subsidiados | EL DIARIO",
             "Quedan 320 apartamentos subsidiados"),
        ]
        for titulo, esperado in casos:
            assert strip_outlet_suffix(titulo) == esperado, titulo

    def test_keeps_legitimate_sentence_fragments(self):
        """Una cola en minúscula es parte de la frase, no un nombre de medio."""
        for titulo in (
            "La reforma pensional - qué sigue ahora",
            "Petro y Maduro - la frontera en disputa",
            "Crisis en el Congreso: el pulso por la reforma",
            "Titular sin separador alguno",
        ):
            assert strip_outlet_suffix(titulo) == titulo, titulo

    def test_never_leaves_a_useless_stub(self):
        """No corta si lo que queda es demasiado corto para ser un titular."""
        assert strip_outlet_suffix("Paz - Indepaz") == "Paz - Indepaz"

    def test_handles_empty_and_none(self):
        assert strip_outlet_suffix("") == ""
        assert strip_outlet_suffix(None) == ""


class TestBuildModelInput:
    def test_prepends_clean_title(self):
        out = build_model_input("Reforma aprobada | EL DIARIO", "El Congreso votó a favor.")
        assert out == "Reforma aprobada\n\nEl Congreso votó a favor."

    def test_does_not_duplicate_a_title_already_in_the_body(self):
        """Trafilatura incluye el titular en el cuerpo en unos medios y en
        otros no (10 de 47 artículos): la forma del input no debe depender
        del CMS de la fuente."""
        out = build_model_input(
            "Reforma aprobada | EL DIARIO",
            "Reforma aprobada | EL DIARIO\nEl Congreso votó a favor.",
        )
        assert out == "Reforma aprobada\n\nEl Congreso votó a favor."
        assert out.count("Reforma aprobada") == 1

    def test_survives_missing_pieces(self):
        assert build_model_input(None, "Solo cuerpo.") == "Solo cuerpo."
        assert build_model_input("", "Solo cuerpo.") == "Solo cuerpo."
        assert build_model_input("Solo titular", "") == "Solo titular"


def test_judge_training_and_api_compose_identically():
    """Las tres etapas deben producir el MISMO texto para el mismo artículo."""
    from src.training.data.dataset import IdeoGraphDataset

    article = {
        "id": "x1",
        "title": "El Senado aprobó la reforma - Concejo de Medellín",
        "text": "El Senado aprobó la reforma pensional en segundo debate. " * 6,
        "label": "institucionalismo",
    }

    # (a) lo que compone el juez / la API
    esperado = build_model_input(article["title"], article["text"])
    assert esperado.startswith("El Senado aprobó la reforma\n\n")
    assert "Concejo de Medellín" not in esperado

    # (b) lo que trocea el entrenamiento: mismo texto, mismos tokens
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "a.jsonl"
        path.write_text(json.dumps(article, ensure_ascii=False) + "\n", encoding="utf-8")
        ds = IdeoGraphDataset(
            path, model_name="dccuchile/bert-base-spanish-wwm-cased",
            chunk_size=512, chunk_stride=384, max_chunks=16,
        )
        del_dataset = ds.tokenizer(esperado, add_special_tokens=False)["input_ids"]
        item = ds[0]
        # 1 chunk: los ids reales (sin CLS/SEP ni padding) deben coincidir
        reales = [
            i for i, m in zip(item["input_ids"][0].tolist(),
                              item["attention_mask"][0].tolist()) if m
        ]
        assert reales[1:-1] == del_dataset[: len(reales) - 2]
