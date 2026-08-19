"""Compuerta de calidad estructural para artículos scrapeados.

Heurísticas baratas (sin LLM) que atrapan lo que el cleaner no puede: páginas
que NO son un artículo aunque tengan texto largo. Detectadas empíricamente en
el corpus (auditoría ago-2026): páginas de sección/listado ("Política: Últimas
noticias, fotos y videos…"), portadas de radio online, ediciones-resumen — 10
de 544 artículos del silver eran de este tipo y contaminaban el entrenamiento.

Se ejecuta en el pipeline DESPUÉS del cleaner y ANTES del filtro LLM (ahorra
llamadas de API en basura obvia). Complementa —no reemplaza— la categoría
`garbage` del filter: esta compuerta es estructural y gratuita.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Títulos de páginas de sección/listado (no de artículos individuales)
_LISTING_TITLE_PATTERN = re.compile(
    r"(?:"
    r"últimas noticias"
    r"|noticias,? fotos y videos"
    r"|noticias y (?:radio|videos|fotos)"
    r"|radio online"
    r"|noticias e información"
    r"|breaking news"
    r"|^noticias de [a-záéíóúñ ]+\|"
    r")",
    re.IGNORECASE,
)

# Umbrales calibrados contra el corpus real (auditoría ago-2026, 544 arts):
# atrapan los 10 listados/portadas conocidos y NO rechazan los casos límite
# legítimos verificados a mano (brief de 2 párrafos de El Nuevo Siglo,
# comunicados ANDI con mal título de trafilatura, especial fragmentado de
# Cuestión Pública). Si se ajustan, re-validar con
# scripts/audit_corpus_quality.py.
MIN_TITLE_CHARS = 8              # informativo (warning), NO rechaza solo
SUBSTANTIAL_PARAGRAPH_CHARS = 80
MAX_SHORT_LINE_RATIO = 0.65      # % de líneas < 40 chars (listados: 0.67-0.98)
MIN_LINES_FOR_RATIO = 8          # el ratio solo aplica con suficientes líneas
MIN_SENTENCE_CLOSURE = 0.25      # % de líneas que cierran oración
MIN_ALPHA_RATIO = 0.55           # % de caracteres alfabéticos (vs UI/números)

_SENTENCE_END = (".", "!", "?", "»", "”", '"', ")")


@dataclass
class QualityVerdict:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def _short_line_ratio(lines: list[str]) -> float:
    return sum(1 for line in lines if len(line) < 40) / max(1, len(lines))


def _sentence_closure_ratio(lines: list[str]) -> float:
    return sum(1 for line in lines if line.endswith(_SENTENCE_END)) / max(1, len(lines))


def _alpha_ratio(text: str) -> float:
    stripped = text.replace(" ", "").replace("\n", "")
    if not stripped:
        return 0.0
    return sum(ch.isalpha() for ch in stripped) / len(stripped)


def assess_article_quality(title: str, text: str) -> QualityVerdict:
    """Evalúa si el texto ES un artículo periodístico coherente.

    Returns:
        QualityVerdict(ok, reasons, metrics). `reasons` usa slugs estables
        (aparecen en los contadores del pipeline como `low_quality:<slug>`).
    """
    reasons: list[str] = []
    warnings: list[str] = []
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    substantial = sum(1 for line in lines if len(line) >= SUBSTANTIAL_PARAGRAPH_CHARS)
    slr = _short_line_ratio(lines)
    closure = _sentence_closure_ratio(lines)
    alpha = _alpha_ratio(text)

    # Título corto/ausente: advertencia, no rechazo (trafilatura a veces da
    # mal título a comunicados legítimos — verificado con la ANDI). El texto
    # es lo que entrena al clasificador.
    if len(title.strip()) < MIN_TITLE_CHARS:
        warnings.append("sin_titulo")

    if _LISTING_TITLE_PATTERN.search(title):
        reasons.append("titulo_de_listado")

    # Estructura de listado: mayoría de líneas cortas Y líneas que no
    # cierran oración (titulares apilados, no prosa)
    if len(lines) >= MIN_LINES_FOR_RATIO and slr > MAX_SHORT_LINE_RATIO and closure < 0.4:
        reasons.append("estructura_de_listado")

    # Prosa sustancial: rechaza con <2 párrafos reales; con exactamente 2,
    # solo si además la prosa no cierra oraciones (un brief legítimo de dos
    # párrafos bien redactados pasa).
    if substantial < 2 or (substantial == 2 and closure < 0.35):
        reasons.append("pocos_parrafos")

    if closure < MIN_SENTENCE_CLOSURE:
        reasons.append("prosa_incompleta")

    if alpha < MIN_ALPHA_RATIO:
        reasons.append("poco_texto_alfabetico")

    return QualityVerdict(
        ok=not reasons,
        reasons=reasons,
        warnings=warnings,
        metrics={
            "n_lines": len(lines),
            "substantial_paragraphs": substantial,
            "short_line_ratio": round(slr, 3),
            "sentence_closure_ratio": round(closure, 3),
            "alpha_ratio": round(alpha, 3),
        },
    )
