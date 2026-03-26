"""LLM-as-a-Judge — etiqueta noticias con scores ideológicos usando un LLM."""

import json
import logging
from pathlib import Path

from src.labeling.codebook import build_system_prompt
from src.models.ideovect_model import AXIS_NAMES
from src.paths import INTERIM_DIR, RAW_DIR

logger = logging.getLogger(__name__)


def parse_response(response_text: str) -> dict | None:
    """Extrae el JSON de la respuesta del LLM.

    Maneja respuestas con o sin bloques ```json```.
    """
    text = response_text.strip()

    # Extraer contenido entre ```json ... ```
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("No se pudo parsear la respuesta del LLM: %s", text[:200])
        return None

    # Validar estructura
    if "is_political" not in data:
        return None
    for axis in AXIS_NAMES:
        if axis not in data:
            return None
        if not isinstance(data[axis], (int, float)):
            return None

    return data


def normalize_labels(data: dict) -> dict:
    """Normaliza los scores de 0-100 a 0-1 para el modelo."""
    return {
        "is_political": int(data["is_political"]),
        "labels": {
            axis: round(data[axis] / 100.0, 4) for axis in AXIS_NAMES
        },
    }


def label_news_file(
    input_path: Path | None = None,
    output_path: Path | None = None,
    llm_client=None,
    llm_model: str = "claude-sonnet-4-20250514",
) -> Path:
    """Etiqueta un archivo de noticias crudas con el LLM-as-a-Judge.

    Args:
        input_path: Archivo JSONL en data/raw/ con campo "text".
        output_path: Archivo JSONL de salida en data/interim/.
        llm_client: Cliente del LLM (ej. anthropic.Anthropic()).
        llm_model: Modelo a usar para el etiquetado.

    Returns:
        Path al archivo etiquetado.

    Formato de entrada (data/raw/):
        {"text": "El presidente anunció...", "source": "eltiempo", "date": "2024-01-15"}

    Formato de salida (data/interim/):
        {"text": "...", "is_political": 1, "labels": {"personalismo": 0.72, ...}}
    """
    if input_path is None:
        input_path = RAW_DIR / "news.jsonl"
    if output_path is None:
        output_path = INTERIM_DIR / "labeled_news.jsonl"

    if llm_client is None:
        raise ValueError(
            "Debes pasar un llm_client (ej. anthropic.Anthropic()). "
            "Instala el SDK con: pip install anthropic"
        )

    system_prompt = build_system_prompt()

    labeled_count = 0
    error_count = 0

    with open(input_path, encoding="utf-8") as fin, \
         open(output_path, "w", encoding="utf-8") as fout:

        for line_num, line in enumerate(fin, 1):
            line = line.strip()
            if not line:
                continue

            raw = json.loads(line)
            text = raw["text"]

            try:
                response = llm_client.messages.create(
                    model=llm_model,
                    max_tokens=512,
                    system=system_prompt,
                    messages=[{"role": "user", "content": text}],
                )

                result = parse_response(response.content[0].text)

                if result is None:
                    logger.warning("Línea %d: respuesta inválida, saltando.", line_num)
                    error_count += 1
                    continue

                normalized = normalize_labels(result)
                output_record = {
                    "text": text,
                    "is_political": normalized["is_political"],
                    "labels": normalized["labels"],
                }

                fout.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                labeled_count += 1

            except Exception:
                logger.exception("Línea %d: error al llamar al LLM.", line_num)
                error_count += 1

    logger.info(
        "Etiquetado completado: %d exitosas, %d errores. Salida: %s",
        labeled_count, error_count, output_path,
    )
    return output_path
