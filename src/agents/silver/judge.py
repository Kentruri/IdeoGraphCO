"""LLM-as-a-Judge — etiqueta noticias con scores ideológicos usando Gemini.

Usa escritura incremental con cursor para no perder trabajo si se interrumpe.
Incluye retry con backoff y rate limiting para el free tier de Gemini.
"""

import json
import logging
import time
from pathlib import Path

from tqdm import tqdm

from src.agents.silver.codebook import build_system_prompt
from src.core.paths import RAW_DIR, SILVER_DIR
from src.core.ids import article_id
from src.core.schema import CLASS_TO_IDX, IDEOLOGY_CLASSES

logger = logging.getLogger(__name__)

# Silenciar logs ruidosos del SDK para no contaminar la barra de tqdm.
for _noisy in ("google_genai", "google_genai.types", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Formato CATEGÓRICO (metodología del anteproyecto, Fase 1 — Etiquetado
# Asistido): el juez asigna la clase ideológica PREDOMINANTE ("dominant")
# además de los 8 scores de intensidad en [0,1], que se conservan como
# señal secundaria para auditoría y análisis. El registro de salida lleva
# `label`/`label_idx` (los que consume el Dataset) + los 8 scores.
AXIS_NAMES: list[str] = IDEOLOGY_CLASSES
DOMINANT_KEY = "dominant"

# Cursor SIDECAR por archivo de salida (<output>.cursor): un cursor global
# único corrompía el estado al etiquetar cualquier otro archivo con --input/
# --output (el cursor de un archivo aplicaba al siguiente).
_LEGACY_CURSOR_PATH = SILVER_DIR / ".silver_cursor"

# Chars del artículo que ve el juez, alineados con lo que el clasificador
# consume de verdad. Antes eran 8.000 (~1.680 tokens con el ratio real del
# corpus, 4,76 chars/token): en el 13,2% de los artículos el juez etiquetaba
# viendo MENOS texto del que después entrena al modelo, lo que mete ruido de
# etiquetado. 15.000 chars ≈ 3.150 tokens y cubre el p95 del corpus (2.928
# tokens). `judge_truncated` deja auditable el caso que aún se recorta.
JUDGE_MAX_CHARS = 15000


# Tras N fallos CONSECUTIVOS del LLM se asume cuota agotada / servicio caído
# y la corrida se detiene SIN avanzar el cursor (el artículo se reintenta en
# la próxima corrida). Sin esto, una cuota agotada "etiquetaba" miles de
# líneas como errores silenciosos, perdiéndolas para siempre.
_MAX_CONSECUTIVE_FAILURES = 5


def _cursor_path_for(output_path: Path) -> Path:
    return Path(str(output_path) + ".cursor")


def _read_cursor(output_path: Path) -> int:
    """Lee la última línea etiquetada (0 si no hay cursor)."""
    cursor_path = _cursor_path_for(output_path)
    if cursor_path.exists():
        return int(cursor_path.read_text().strip())
    # Migración: el cursor global viejo solo aplica a la salida por defecto.
    if output_path == SILVER_DIR / "silver_set.jsonl" and _LEGACY_CURSOR_PATH.exists():
        value = int(_LEGACY_CURSOR_PATH.read_text().strip())
        cursor_path.write_text(str(value))
        _LEGACY_CURSOR_PATH.unlink()
        return value
    return 0


def _write_cursor(output_path: Path, line_num: int) -> None:
    """Guarda la última línea etiquetada."""
    _cursor_path_for(output_path).write_text(str(line_num))


def _append_failed(output_path: Path, line_num: int, url: str) -> None:
    """Registra la línea fallida en <output>.failed para reintento dirigido."""
    failed_path = Path(str(output_path) + ".failed")
    with open(failed_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"line": line_num, "url": url}) + "\n")


def parse_response(response_text: str) -> dict | None:
    """Extrae el JSON de la respuesta del LLM y valida la escala continua [0, 1].

    Acepta tanto JSON crudo como envuelto en ```json ... ```. Cada eje debe
    ser un número (entero o float) directamente en [0.0, 1.0]. Valores
    fuera de rango se acotan.
    """
    text = response_text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(
            "No se pudo parsear respuesta (%s). Texto recibido (%d chars): %s",
            e, len(text), text[:600],
        )
        return None

    for axis in AXIS_NAMES:
        if axis not in data:
            return None
        if not isinstance(data[axis], (int, float)):
            return None
        # Acotar a [0.0, 1.0] como float.
        data[axis] = max(0.0, min(1.0, float(data[axis])))

    # Clase dominante: obligatoria y dentro de las 8 clases. Una respuesta
    # sin dominante válida se descarta completa (mejor reintentar que
    # inventar la etiqueta con argmax).
    dominant = data.get(DOMINANT_KEY)
    if dominant not in CLASS_TO_IDX:
        logger.warning("Respuesta sin clase dominante válida: %r", dominant)
        return None

    return data


def normalize_labels(data: dict) -> dict:
    """Devuelve los scores tal cual (ya están en [0, 1]).

    Antes esta función mapeaba 1-5 → [0, 1]. Ahora el LLM da el score
    directamente en la escala objetivo del modelo. La función queda como
    pasaje + redondeo a 4 decimales para limpiar ruido flotante.
    """
    return {axis: round(float(data[axis]), 4) for axis in AXIS_NAMES}


# Schema JSON estructurado para Gemini: 8 ejes numéricos en [0, 1] + la
# clase dominante como enum de las 8 clases. Garantiza tipos y rango,
# eliminando la mayoría de la validación defensiva.
_LABEL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        **{
            axis: {"type": "number", "minimum": 0.0, "maximum": 1.0}
            for axis in AXIS_NAMES
        },
        DOMINANT_KEY: {"type": "string", "enum": list(AXIS_NAMES)},
    },
    "required": [*AXIS_NAMES, DOMINANT_KEY],
}


def _call_gemini_with_retry(
    client,
    model: str,
    system_prompt: str,
    text: str,
    max_retries: int = 3,
) -> str | None:
    """Llama a Gemini con retry y backoff exponencial.

    Configuración clave para Gemini 2.5 (reasoning models):
    - response_mime_type=application/json → fuerza JSON válido, no markdown
    - thinking_budget=0 → desactiva chain-of-thought interno (no lo necesitamos
      para seguir un codebook estructurado, y los tokens del thinking compiten
      con max_output_tokens, truncando el JSON)
    - max_output_tokens=1024 → margen de sobra para el JSON con 9 campos
    """
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config={
                    "system_instruction": system_prompt,
                    "response_mime_type": "application/json",
                    "response_schema": _LABEL_RESPONSE_SCHEMA,
                    "thinking_config": {"thinking_budget": 0},
                    "max_output_tokens": 2048,
                    "temperature": 0.1,  # baja temperatura para consistencia
                },
            )
            return response.text
        except Exception as e:
            error_msg = str(e)
            # Rate limit: esperar más
            if "429" in error_msg or "quota" in error_msg.lower():
                wait = 60  # esperar 1 minuto en rate limit
                logger.warning("Rate limit alcanzado. Esperando %ds...", wait)
            else:
                wait = 2 ** (attempt + 1)
                logger.warning(
                    "Error intento %d/%d: %s. Esperando %ds...",
                    attempt + 1, max_retries, error_msg[:100], wait,
                )
            time.sleep(wait)
    return None


def label_news_file(
    llm_client,
    input_path: Path | None = None,
    output_path: Path | None = None,
    llm_model: str = "gemini-2.5-flash",
    force: bool = False,
    max_articles: int | None = None,
    rate_limit_delay: float = 4.5,
) -> Path:
    """Etiqueta un archivo de noticias con Gemini como juez.

    Usa cursor incremental para continuar donde se quedó si se interrumpe.

    Args:
        llm_client: Cliente de Google GenAI (google.genai.Client()).
        input_path: JSONL de entrada (default: data/raw/articles.jsonl).
        output_path: JSONL de salida (default: data/silver/silver_set.jsonl).
        llm_model: Modelo de Gemini a usar.
        force: Si True, re-etiqueta todo desde cero.
        max_articles: Límite de artículos a etiquetar (None = todos).
        rate_limit_delay: Segundos entre requests (4.5s = ~13 RPM, bajo el límite de 15).

    Returns:
        Path al archivo etiquetado.
    """
    if input_path is None:
        input_path = RAW_DIR / "articles.jsonl"
    if output_path is None:
        output_path = SILVER_DIR / "silver_set.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if force:
        # Resetear el cursor ANTES de truncar la salida: interrumpir entre el
        # open("w") y el primer artículo dejaba salida vacía + cursor viejo
        # (la siguiente corrida "continuaba" saltándose todo lo truncado).
        _write_cursor(output_path, 0)
        cursor = 0
    else:
        cursor = _read_cursor(output_path)
        if output_path.exists() and output_path.stat().st_size > 0:
            with open(output_path, encoding="utf-8") as f:
                first = json.loads(f.readline())
            if "label" not in first:
                raise SystemExit(
                    f"{output_path} tiene formato LEGACY (continuo, sin 'label'): "
                    "appendear registros categóricos lo dejaría mixto. "
                    "Re-etiqueta desde cero con --force."
                )
            if cursor == 0:
                raise SystemExit(
                    f"{output_path} tiene contenido pero el cursor está en 0 "
                    "(estado inconsistente): appendear duplicaría artículos. "
                    "Usa --force para re-etiquetar desde cero."
                )
    mode = "w" if force else "a"

    with open(input_path, encoding="utf-8") as f:
        total_lines = sum(1 for _ in f)

    pending = total_lines - cursor
    if max_articles is not None:
        pending = min(pending, max_articles)

    if pending <= 0:
        logger.info("Todo etiquetado. %d artículos procesados, 0 pendientes.", cursor)
        return output_path

    logger.info(
        "Artículos: %d total | %d ya etiquetados | %d pendientes",
        total_lines, cursor, pending,
    )
    logger.info("Rate limit: %.1fs entre requests (~%.0f RPM)", rate_limit_delay, 60 / rate_limit_delay)

    system_prompt = build_system_prompt(include_examples=True)
    labeled_count = 0
    error_count = 0
    consecutive_failures = 0

    pbar = tqdm(
        total=pending,
        desc="Etiquetando",
        unit="art",
        smoothing=0.1,
        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]",
    )

    try:
        with open(input_path, encoding="utf-8") as fin, \
             open(output_path, mode, encoding="utf-8") as fout:

            for i, line in enumerate(fin):
                if i < cursor:
                    continue

                if max_articles is not None and labeled_count >= max_articles:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    raw = json.loads(line)
                    text = raw["text"]
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # Línea corrupta = permanente: saltar avanzando el cursor
                    # (sin esto abortaba el etiquetado y quedaba en bucle).
                    logger.warning("Línea %d corrupta (%s), saltando.", i + 1, e)
                    error_count += 1
                    _write_cursor(output_path, i + 1)
                    continue

                # Truncar textos muy largos (ahorro de tokens)
                if len(text) > JUDGE_MAX_CHARS:
                    text = text[:JUDGE_MAX_CHARS]

                # Llamar a Gemini
                response_text = _call_gemini_with_retry(
                    client=llm_client,
                    model=llm_model,
                    system_prompt=system_prompt,
                    text=text,
                )

                if response_text is None:
                    consecutive_failures += 1
                    if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                        # Cuota agotada o servicio caído: NO avanzar el cursor
                        # (este artículo se reintenta) y detener la corrida.
                        logger.error(
                            "%d fallos consecutivos del LLM: deteniendo. El "
                            "cursor queda en %d; reintenta cuando la cuota se "
                            "restablezca.", consecutive_failures, i,
                        )
                        break
                    logger.warning("Línea %d: falló tras reintentos, saltando.", i + 1)
                    _append_failed(output_path, i + 1, raw.get("url", ""))
                    error_count += 1
                    _write_cursor(output_path, i + 1)
                    pbar.update(1)
                    pbar.set_postfix(ok=labeled_count, err=error_count)
                    continue
                consecutive_failures = 0

                result = parse_response(response_text)
                if result is None:
                    logger.warning("Línea %d: respuesta inválida, saltando.", i + 1)
                    _append_failed(output_path, i + 1, raw.get("url", ""))
                    error_count += 1
                    _write_cursor(output_path, i + 1)
                    pbar.update(1)
                    pbar.set_postfix(ok=labeled_count, err=error_count)
                    continue

                normalized = normalize_labels(result)
                dominant = result[DOMINANT_KEY]

                # id estable: si el input ya lo trae, lo preservamos; si no, lo
                # derivamos del URL. Mismo URL → mismo id, siempre.
                record_id = raw.get("id") or article_id(raw.get("url", ""))

                output_record = {
                    "id": record_id,
                    "text": raw["text"],
                    "title": raw.get("title", ""),
                    "source": raw.get("source", ""),
                    "category": raw.get("category", ""),
                    "url": raw.get("url", ""),
                    "date": raw.get("date"),
                    # Etiqueta categórica (la que consume el Dataset)
                    "label": dominant,
                    "label_idx": CLASS_TO_IDX[dominant],
                    "label_source": "silver-llm",
                    "judge_model": llm_model,
                    # Marca si el juez vio el texto recortado: permite medir
                    # en el OE3 si esos casos concentran errores.
                    "judge_truncated": len(raw["text"]) > JUDGE_MAX_CHARS,
                    # Scores de intensidad (señal secundaria: auditoría/análisis)
                    **{axis: normalized[axis] for axis in AXIS_NAMES},
                }

                fout.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                fout.flush()
                labeled_count += 1
                _write_cursor(output_path, i + 1)

                pbar.update(1)
                pbar.set_postfix(ok=labeled_count, err=error_count)

                # Rate limiting
                time.sleep(rate_limit_delay)
    finally:
        pbar.close()

    logger.info(
        "Etiquetado completado: %d exitosos, %d errores. Salida: %s",
        labeled_count, error_count, output_path,
    )
    return output_path
