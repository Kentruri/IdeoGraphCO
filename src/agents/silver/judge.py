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
from src.core.paths import INTERIM_DIR, RAW_DIR
from src.core.ids import article_id

logger = logging.getLogger(__name__)

# Silenciar logs ruidosos del SDK para no contaminar la barra de tqdm.
for _noisy in ("google_genai", "google_genai.types", "httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

AXIS_NAMES: list[str] = [
    "personalismo", "institucionalismo", "populismo", "doctrinarismo",
    "soberanismo", "globalismo", "conservadurismo", "progresismo",
]

CURSOR_PATH = INTERIM_DIR / ".label_cursor"


def _read_cursor() -> int:
    """Lee la última línea etiquetada (0 si no hay cursor)."""
    if CURSOR_PATH.exists():
        return int(CURSOR_PATH.read_text().strip())
    return 0


def _write_cursor(line_num: int) -> None:
    """Guarda la última línea etiquetada."""
    CURSOR_PATH.write_text(str(line_num))


def parse_response(response_text: str) -> dict | None:
    """Extrae el JSON de la respuesta del LLM y valida la escala 1-5.

    Acepta tanto JSON crudo como envuelto en ```json ... ```.
    Cada eje debe ser un entero (o float redondeable) en [1, 5].
    Si is_political=0, fuerza todos los ejes a 1 (Ausente) en consistencia
    con la regla 4 del codebook.
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

    if "is_political" not in data:
        return None
    is_political = int(data["is_political"])

    for axis in AXIS_NAMES:
        if axis not in data:
            return None
        if not isinstance(data[axis], (int, float)):
            return None
        # Redondear y acotar a la escala 1-5 (tolera floats por seguridad).
        data[axis] = max(1, min(5, int(round(data[axis]))))

    # Consistencia con regla 4: no-políticos → todos los ejes en 1 (Ausente).
    if is_political == 0:
        for axis in AXIS_NAMES:
            data[axis] = 1

    data["is_political"] = is_political
    return data


# Mapeo lineal de la escala 1-5 a [0, 1] (paso de 0.25).
_SCALE_TO_UNIT: dict[int, float] = {1: 0.0, 2: 0.25, 3: 0.5, 4: 0.75, 5: 1.0}


def normalize_labels(data: dict) -> dict:
    """Mapea la escala 1-5 del codebook a [0, 1] para el modelo.

    1 (Ausente)   → 0.00
    2 (Leve)      → 0.25
    3 (Moderado)  → 0.50
    4 (Marcado)   → 0.75
    5 (Dominante) → 1.00
    """
    return {
        "is_political": int(data["is_political"]),
        **{axis: _SCALE_TO_UNIT[int(data[axis])] for axis in AXIS_NAMES},
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
        input_path: JSONL de entrada (default: data/raw/news_clean.jsonl).
        output_path: JSONL de salida (default: data/interim/labeled_news.jsonl).
        llm_model: Modelo de Gemini a usar.
        force: Si True, re-etiqueta todo desde cero.
        max_articles: Límite de artículos a etiquetar (None = todos).
        rate_limit_delay: Segundos entre requests (4.5s = ~13 RPM, bajo el límite de 15).

    Returns:
        Path al archivo etiquetado.
    """
    if input_path is None:
        input_path = RAW_DIR / "news_clean.jsonl"
    if output_path is None:
        output_path = INTERIM_DIR / "labeled_news.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cursor = 0 if force else _read_cursor()
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

                raw = json.loads(line)
                text = raw["text"]

                # Truncar textos muy largos (ahorro de tokens)
                if len(text) > 8000:
                    text = text[:8000]

                # Llamar a Gemini
                response_text = _call_gemini_with_retry(
                    client=llm_client,
                    model=llm_model,
                    system_prompt=system_prompt,
                    text=text,
                )

                if response_text is None:
                    logger.warning("Línea %d: falló tras reintentos, saltando.", i + 1)
                    error_count += 1
                    _write_cursor(i + 1)
                    pbar.update(1)
                    pbar.set_postfix(ok=labeled_count, err=error_count)
                    continue

                result = parse_response(response_text)
                if result is None:
                    logger.warning("Línea %d: respuesta inválida, saltando.", i + 1)
                    error_count += 1
                    _write_cursor(i + 1)
                    pbar.update(1)
                    pbar.set_postfix(ok=labeled_count, err=error_count)
                    continue

                normalized = normalize_labels(result)

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
                    "is_political": normalized["is_political"],
                    **{axis: normalized[axis] for axis in AXIS_NAMES},
                }

                fout.write(json.dumps(output_record, ensure_ascii=False) + "\n")
                fout.flush()
                labeled_count += 1
                _write_cursor(i + 1)

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
