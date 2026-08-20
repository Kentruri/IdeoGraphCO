"""Integración con Label Studio (Community Edition) para el gold set v2.

Label Studio es la herramienta de anotación; este módulo es el puente con el
pipeline del proyecto, en tres piezas:

1. `build_labeling_config()` — la plantilla XML de la interfaz. Por defecto
   pide SOLO la clase dominante (una decisión por artículo), que es lo único
   que consume el clasificador multiclase. Las escalas 1-5 por eje son
   opcionales (`with_scales=True`): venían del diseño anterior de regresión
   sobre 8 ejes y multiplican por 9 el trabajo del anotador.
2. `write_tasks()` — convierte los artículos del gold en el archivo de tareas
   que Label Studio importa. Deliberadamente NO incluye `source`, `category`
   ni `url`: el codebook exige juzgar por el texto, y conocer el medio sesga
   al anotador (en el libro de Excel esas columnas quedaban a la vista).
3. `parse_export()` — lee el export JSON de Label Studio y lo devuelve en el
   MISMO formato que produce `read_book()` de scripts/ingest_gold.py, así el
   cálculo del α de Krippendorff y el flujo de consenso no cambian.

Flujo completo (detallado en workflows-guide/04-gold-set.md):

    python scripts/prepare_gold_set.py            # genera tareas LS + Excel
    # cada anotador: label-studio start → importar sus tareas → anotar
    # → exportar como JSON a annotation/gold_set_v2_<anotador>.json
    python scripts/ingest_gold.py --books annotation/gold_set_v2_kevin.json \
        annotation/gold_set_v2_juan.json

El export soportado es el formato "JSON" de Label Studio (lista de tareas con
`data` y `annotations[].result`), no el "JSON-MIN".
"""

from __future__ import annotations

import json
from pathlib import Path

from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES

AXES: list[str] = IDEOLOGY_CLASSES

# ---------------------------------------------------------------------------
# Plantilla de la interfaz (se pega en Label Studio → Labeling Interface)
# ---------------------------------------------------------------------------
# - Rating 1-5 por eje, NO obligatorio (la instrucción del codebook permite
#   dejar un eje en duda para completarlo al final; 0 estrellas = sin anotar).
# - clase_dominante obligatoria y única: es la etiqueta que consume el
#   clasificador y el número sobre el que se calcula el α del anteproyecto.
# - El texto se muestra completo; el título como encabezado.

_AXIS_LABELS: list[tuple[str, str]] = [
    ("personalismo", "Personalismo — líder individual como eje central"),
    ("institucionalismo", "Institucionalismo — instituciones y procesos formales"),
    ("populismo", "Populismo — dicotomía pueblo vs. élite"),
    ("doctrinarismo", "Doctrinarismo — cuerpo ideológico como autoridad"),
    ("soberanismo", "Soberanismo — autonomía nacional, rechazo a injerencia"),
    ("globalismo", "Globalismo — multilateralismo, normas globales"),
    ("conservadurismo", "Conservadurismo — tradición, orden, autoridad"),
    ("progresismo", "Progresismo — justicia social, derechos, reformas"),
]

# Etiquetas legibles de cada clase en los botones de la interfaz.
_CLASS_HINTS: dict[str, str] = {
    "personalismo": "líder individual como eje central",
    "institucionalismo": "instituciones y procesos formales",
    "populismo": "dicotomía pueblo vs. élite",
    "doctrinarismo": "cuerpo ideológico como autoridad",
    "soberanismo": "autonomía nacional, anti-injerencia",
    "globalismo": "multilateralismo, normas globales",
    "conservadurismo": "tradición, orden, autoridad",
    "progresismo": "justicia social, derechos, reformas",
}


def build_labeling_config(with_scales: bool = False) -> str:
    """Plantilla XML de la interfaz de anotación.

    Args:
        with_scales: si True, añade los 8 ratings de intensidad 1-5. Por
            defecto False: el clasificador es multiclase single-label y solo
            consume la clase dominante, así que pedir 9 decisiones por
            artículo en vez de 1 multiplica el esfuerzo sin alimentar al
            modelo. Las escalas eran un residuo del diseño de regresión.
    """
    choices = "\n".join(
        f'      <Choice value="{cls}" hint="{_CLASS_HINTS[cls]}"/>'
        for cls in IDEOLOGY_CLASSES
    )

    ratings_block = ""
    if with_scales:
        ratings = "\n".join(
            f'    <View style="display:flex;align-items:center;gap:12px;margin:2px 0">\n'
            f'      <Header size="5" value="{label}"/>\n'
            f'      <Rating name="{axis}" toName="text" maxRating="5" icon="star" size="medium"/>\n'
            f"    </View>"
            for axis, label in _AXIS_LABELS
        )
        ratings_block = (
            '\n  <Header size="4" value="Intensidad por eje '
            '(1 ausente … 5 dominante; vacío = sin decidir)"/>\n'
            f"{ratings}\n"
        )

    return f"""<View>
  <Header size="3" value="$title"/>
  <View style="max-height:460px;overflow-y:auto;border:1px solid #ddd;padding:12px;border-radius:4px;background:#fafafa">
    <Text name="text" value="$text" granularity="paragraph"/>
  </View>
{ratings_block}
  <Header size="4" value="CLASE DOMINANTE: el encuadre que ESTRUCTURA el argumento del texto"/>
  <Choices name="clase_dominante" toName="text" choice="single" required="true"
           requiredMessage="La clase dominante es obligatoria (metodología del anteproyecto)">
{choices}
  </Choices>

  <Header size="4" value="Notas (dudas, empates, razones — alimentan la sesión de consenso)"/>
  <TextArea name="notes" toName="text" rows="3" maxSubmissions="1" editable="true"
            placeholder="Opcional: por qué dudaste, qué clases empataban, etc."/>
</View>"""


# Plantilla por defecto (solo clase dominante).
LABELING_CONFIG: str = build_labeling_config(with_scales=False)


# ---------------------------------------------------------------------------
# Tareas: gold set → archivo que importa Label Studio
# ---------------------------------------------------------------------------

def build_tasks(articles: list[dict]) -> list[dict]:
    """Convierte artículos en tareas de Label Studio.

    Solo id, título y texto: la fuente, la categoría y la URL se OMITEN a
    propósito para que la anotación sea ciega al medio.
    """
    tasks = []
    for article in articles:
        tasks.append({
            "data": {
                "id": article["id"],
                "title": article.get("title", "") or "(sin título)",
                "text": article["text"],
            }
        })
    return tasks


def write_tasks(articles: list[dict], path: Path) -> Path:
    """Escribe el archivo de tareas de un anotador."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(build_tasks(articles), f, ensure_ascii=False, indent=1)
    return path


def write_labeling_config(path: Path, with_scales: bool = False) -> Path:
    """Escribe la plantilla XML para pegar en Label Studio."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_labeling_config(with_scales), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Export: JSON de Label Studio → formato de read_book()
# ---------------------------------------------------------------------------

def _result_items(task: dict) -> list[dict]:
    """Items de la ÚLTIMA anotación completada de la tarea (no cancelada).

    Si el anotador guardó varias veces, Label Studio acumula anotaciones; la
    última refleja su decisión final.
    """
    annotations = [
        a for a in task.get("annotations", []) if not a.get("was_cancelled")
    ]
    if not annotations:
        return []
    return annotations[-1].get("result", []) or []


def parse_export(path: Path) -> dict[str, dict]:
    """Lee un export JSON de Label Studio.

    Returns:
        {id: {"dominant": str|None, "scores": {eje: int|None}, "notes": str}}
        — idéntico a read_book() de scripts/ingest_gold.py, para que el α y
        el consenso funcionen sin cambios.
    """
    with open(path, encoding="utf-8") as f:
        tasks = json.load(f)
    if not isinstance(tasks, list):
        raise ValueError(
            f"{path}: se esperaba el export 'JSON' de Label Studio (una lista "
            "de tareas). El formato 'JSON-MIN' no está soportado."
        )

    annotations: dict[str, dict] = {}
    for task in tasks:
        data = task.get("data") or {}
        article_id = str(data.get("id") or "").strip()
        if not article_id:
            continue

        scores: dict[str, int | None] = {axis: None for axis in AXES}
        dominant: str | None = None
        notes = ""

        for item in _result_items(task):
            name = item.get("from_name", "")
            value = item.get("value") or {}
            if name in scores:
                rating = value.get("rating")
                if isinstance(rating, (int, float)) and 1 <= rating <= 5:
                    scores[name] = int(rating)
                # rating 0 = estrellas sin tocar → queda None (eje sin anotar)
            elif name == "clase_dominante":
                choices = value.get("choices") or []
                if choices:
                    candidate = str(choices[0]).strip().lower()
                    if candidate in CLASS_TO_IDX:
                        dominant = candidate
            elif name == "notes":
                texts = value.get("text") or []
                notes = " ".join(str(t) for t in texts if t).strip()

        annotations[article_id] = {
            "dominant": dominant,
            "scores": scores,
            "notes": notes,
        }
    return annotations
