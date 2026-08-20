"""Composición canónica del texto que consume el modelo.

Fuente ÚNICA de verdad para las tres etapas que tocan la etiqueta: el juez
que la asigna (`agents/silver/judge.py`), el entrenamiento que la aprende
(`training/data/dataset.py`) y la inferencia que la predice
(`inference/api.py`). Antes cada una componía su entrada por separado y no
coincidían: el juez y el entrenamiento veían solo `text`, mientras la API
antependía el titular — train/serve skew silencioso.

El titular SÍ entra, por dos razones:

- El codebook define la clase dominante preguntando "¿qué retórica organiza
  EL TITULAR y el primer tercio del texto?" — es parte explícita del criterio
  de anotación.
- Es la parte más cargada ideológicamente del artículo ("Gobierno entrega"
  frente a "Régimen impone" sobre el mismo hecho).

Y se le quita el sufijo del medio ("… | CONtexto Ganadero", "… - Indepaz"):
es una cadena constante por fuente, así que dejarla convertiría al titular en
una huella del medio que el clasificador podría usar como atajo en vez de
aprender ideología.
"""

from __future__ import annotations

import re

# Cola tras un separador al final del titular: candidata a nombre del medio.
_TITLE_TAIL = re.compile(r"\s+[|–—·]\s+([^|–—·]{1,45})$|\s+-\s+([^-]{1,45})$")

# Palabras funcionales que un nombre de medio puede llevar en minúscula
# ("Concejo de Medellín", "Voz de América").
_MINOR_WORDS = {
    "de", "del", "la", "el", "los", "las", "y", "e", "en", "al", "a",
    "para", "por", "con", "the", "of",
}

_SENTENCE_END = (".", "?", "!", ":", ";", ",")


def strip_outlet_suffix(title: str) -> str:
    """Quita el nombre del medio del final del titular, si lo lleva.

    Solo corta cuando la cola parece un NOMBRE (todas sus palabras
    capitalizadas o funcionales) y no un fragmento de la frase: así
    "… | CONtexto Ganadero" y "… - Concejo de Medellín" se limpian, pero
    "La reforma pensional - qué sigue ahora" queda intacto.
    """
    title = (title or "").strip()
    match = _TITLE_TAIL.search(title)
    if not match:
        return title

    tail = (match.group(1) or match.group(2) or "").strip()
    if not tail or tail.endswith(_SENTENCE_END):
        return title

    words = [w for w in tail.split() if w]
    if not words:
        return title
    looks_like_name = all(
        word[0].isupper() or word.lower() in _MINOR_WORDS for word in words
    )
    if not looks_like_name:
        return title

    stripped = title[: match.start()].rstrip()
    # No dejar el titular vacío ni reducirlo a un resto inservible.
    return stripped if len(stripped) >= 10 else title


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip().lower()


def build_model_input(title: str | None, text: str) -> str:
    """Texto canónico: `titular limpio` + línea en blanco + cuerpo.

    Si el cuerpo ya arranca con el titular (trafilatura lo incluye en unos
    medios y en otros no — 10 de 47 artículos en la auditoría de ago-2026),
    esa primera línea se reemplaza por la versión limpia, para que la forma
    del input no dependa del CMS de la fuente.
    """
    body = (text or "").strip()
    clean_title = strip_outlet_suffix(title or "")
    if not clean_title:
        return body
    if not body:
        return clean_title

    first_line, _, rest = body.partition("\n")
    if _normalize(strip_outlet_suffix(first_line)) == _normalize(clean_title):
        body = rest.lstrip("\n")

    return f"{clean_title}\n\n{body}" if body else clean_title
