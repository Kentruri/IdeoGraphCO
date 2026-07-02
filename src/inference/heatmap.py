"""Visualización de mapa de calor — distribución P(clase | doc) sobre 8 ideologías.

Reemplaza el radar chart del diseño anterior. El PDF (Fase 4) especifica mapa
de calor sobre las probabilidades del clasificador.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go

from src.core.schema import IDEOLOGY_CLASSES

# Etiquetas legibles.
CLASS_LABELS: dict[str, str] = {
    "personalismo": "Personalismo",
    "institucionalismo": "Institucionalismo",
    "populismo": "Populismo",
    "doctrinarismo": "Doctrinarismo",
    "soberanismo": "Soberanismo",
    "globalismo": "Globalismo",
    "conservadurismo": "Conservadurismo",
    "progresismo": "Progresismo",
}


def create_heatmap(
    probabilities: dict[str, float],
    title: str = "Distribución ideológica",
) -> go.Figure:
    """Crea un mapa de calor 1×8 con la distribución de probabilidades.

    Args:
        probabilities: dict {clase: probabilidad_pct} — salida de
            IdeoClassifierPredictor.predict()["probabilities"].
        title: título del gráfico.
    """
    labels = [CLASS_LABELS[c] for c in IDEOLOGY_CLASSES]
    values = [probabilities.get(c, 0.0) for c in IDEOLOGY_CLASSES]

    fig = go.Figure(data=go.Heatmap(
        z=[values],
        x=labels,
        y=["P(clase | doc)"],
        colorscale="Viridis",
        zmin=0, zmax=100,
        colorbar=dict(title="%"),
        text=[[f"{v:.1f}%" for v in values]],
        texttemplate="%{text}",
        textfont=dict(size=12, color="white"),
    ))
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis=dict(tickangle=-30),
        width=800, height=250,
    )
    return fig


def create_heatmap_grid(
    results: list[dict],
    row_labels: list[str],
    title: str = "Comparación ideológica",
) -> go.Figure:
    """Mapa de calor N×8 comparando N documentos/medios.

    Args:
        results: lista de dicts {clase: prob_pct} (salida de predictor.predict()).
        row_labels: nombres de filas (uno por documento/medio).
        title: título del gráfico.
    """
    labels = [CLASS_LABELS[c] for c in IDEOLOGY_CLASSES]
    z = [[r.get(c, 0.0) for c in IDEOLOGY_CLASSES] for r in results]
    text = [[f"{v:.1f}%" for v in row] for row in z]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=labels,
        y=row_labels,
        colorscale="Viridis",
        zmin=0, zmax=100,
        colorbar=dict(title="%"),
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=10, color="white"),
    ))
    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        xaxis=dict(tickangle=-30),
        width=850,
        height=max(300, 60 * len(row_labels) + 120),
    )
    return fig


def save_chart(fig: go.Figure, path: str | Path, format: str = "html") -> None:
    """Guarda el gráfico en disco.

    Args:
        format: "html" (interactivo) o "png"/"pdf" (estático, requiere kaleido).
    """
    path = Path(path)
    if format == "html":
        fig.write_html(str(path))
    else:
        fig.write_image(str(path), format=format)
