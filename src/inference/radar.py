"""Visualización de radar chart — representa la huella ideológica de una noticia."""

from pathlib import Path

import plotly.graph_objects as go

from src.models.ideovect_model import AXIS_NAMES

# Etiquetas legibles para el gráfico
AXIS_LABELS: dict[str, str] = {
    "personalismo": "Personalismo",
    "institucionalismo": "Institucionalismo",
    "populismo": "Populismo",
    "doctrinarismo": "Doctrinarismo",
    "soberanismo": "Soberanismo",
    "globalismo": "Globalismo",
    "conservadurismo": "Conservadurismo",
    "progresismo": "Progresismo",
}


def create_radar_chart(
    axes: dict[str, float],
    title: str = "Huella Ideológica",
    fill_color: str = "rgba(99, 110, 250, 0.3)",
    line_color: str = "rgb(99, 110, 250)",
) -> go.Figure:
    """Crea un radar chart interactivo con Plotly.

    Args:
        axes: Dict con scores por eje (0-100). Salida de predictor.predict()["axes"].
        title: Título del gráfico.
        fill_color: Color de relleno del área.
        line_color: Color de la línea del borde.

    Returns:
        Figura de Plotly lista para mostrar o exportar.
    """
    labels = [AXIS_LABELS[name] for name in AXIS_NAMES]
    values = [axes.get(name, 0.0) for name in AXIS_NAMES]

    # Cerrar el polígono (repetir el primer valor al final)
    labels_closed = labels + [labels[0]]
    values_closed = values + [values[0]]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=labels_closed,
        fill="toself",
        fillcolor=fill_color,
        line=dict(color=line_color, width=2),
        name="Intensidad",
    ))

    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[0, 25, 50, 75, 100],
                ticktext=["0", "25", "50", "75", "100"],
            ),
        ),
        showlegend=False,
        width=600,
        height=500,
    )

    return fig


def compare_radar_charts(
    results: list[dict],
    names: list[str],
    title: str = "Comparación Ideológica",
) -> go.Figure:
    """Superpone múltiples huellas ideológicas en un solo radar chart.

    Args:
        results: Lista de dicts con scores (salida de predictor.predict()["axes"]).
        names: Nombres para la leyenda (ej. nombres de medios).
        title: Título del gráfico.
    """
    colors = [
        ("rgba(99, 110, 250, 0.2)", "rgb(99, 110, 250)"),
        ("rgba(239, 85, 59, 0.2)", "rgb(239, 85, 59)"),
        ("rgba(0, 204, 150, 0.2)", "rgb(0, 204, 150)"),
        ("rgba(171, 99, 250, 0.2)", "rgb(171, 99, 250)"),
        ("rgba(255, 161, 90, 0.2)", "rgb(255, 161, 90)"),
    ]

    labels = [AXIS_LABELS[name] for name in AXIS_NAMES]
    labels_closed = labels + [labels[0]]

    fig = go.Figure()

    for i, (axes, name) in enumerate(zip(results, names)):
        fill_c, line_c = colors[i % len(colors)]
        values = [axes.get(ax, 0.0) for ax in AXIS_NAMES]
        values_closed = values + [values[0]]

        fig.add_trace(go.Scatterpolar(
            r=values_closed,
            theta=labels_closed,
            fill="toself",
            fillcolor=fill_c,
            line=dict(color=line_c, width=2),
            name=name,
        ))

    fig.update_layout(
        title=dict(text=title, x=0.5, font=dict(size=16)),
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                tickvals=[0, 25, 50, 75, 100],
            ),
        ),
        showlegend=True,
        width=700,
        height=550,
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
