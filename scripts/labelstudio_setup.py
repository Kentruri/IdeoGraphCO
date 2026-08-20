"""Carga el gold set en Label Studio: crea los proyectos e importa las tareas.

Evita la configuración manual: en vez de crear el proyecto a mano, pegar la
plantilla XML y subir el archivo, este script lo hace por la API.

Requisitos:
  1. Label Studio corriendo (ver workflows-guide/04-gold-set.md).
  2. `python scripts/prepare_gold_set.py` ya ejecutado (genera las tareas).

Uso:
    # 1) el servidor, en otra terminal:
    LABEL_STUDIO_BASE_DATA_DIR=~/label-studio-data \\
        ~/label-studio-env/bin/label-studio start --port 8080

    # 2) cargar los proyectos:
    python scripts/labelstudio_setup.py --annotators kevin juan \\
        --user tu@correo.com --password tu_clave

    # con escalas 1-5 además de la clase dominante:
    python scripts/labelstudio_setup.py --annotators kevin juan --with-scales

    # reemplazar proyectos ya existentes (BORRA sus anotaciones):
    python scripts/labelstudio_setup.py --annotators kevin juan --replace

Nota sobre autenticación: Label Studio 1.23+ desactivó los tokens de API
"legacy", así que se usa la sesión web (login + CSRF) en vez de un token.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.agents.gold import labelstudio  # noqa: E402
from src.core.paths import ROOT  # noqa: E402

PROJECT_PREFIX = "Gold set"


def login(base_url: str, email: str, password: str) -> requests.Session:
    """Sesión autenticada contra Label Studio."""
    session = requests.Session()
    try:
        session.get(f"{base_url}/user/login/", timeout=20)
    except requests.RequestException as exc:
        raise SystemExit(
            f"✗ No responde Label Studio en {base_url}\n"
            f"  ({type(exc).__name__})\n"
            "  Arráncalo primero:\n"
            "    LABEL_STUDIO_BASE_DATA_DIR=~/label-studio-data \\\n"
            "        ~/label-studio-env/bin/label-studio start --port 8080"
        ) from exc

    response = session.post(
        f"{base_url}/user/login/",
        data={
            "email": email,
            "password": password,
            "csrfmiddlewaretoken": session.cookies.get("csrftoken"),
        },
        headers={"Referer": f"{base_url}/user/login/"},
        timeout=30,
    )
    # Label Studio responde 200 con el formulario de nuevo si las credenciales
    # fallan, en vez de un 4xx: se detecta por la ausencia del cookie de sesión.
    if response.status_code >= 400 or not session.cookies.get("sessionid"):
        raise SystemExit(
            f"✗ Login rechazado para {email}. Revisa usuario y contraseña "
            f"(las creaste al abrir {base_url} por primera vez)."
        )
    return session


def _headers(session: requests.Session, base_url: str) -> dict:
    return {
        "X-CSRFToken": session.cookies.get("csrftoken"),
        "Referer": base_url,
        "Content-Type": "application/json",
    }


def existing_projects(session: requests.Session, base_url: str) -> dict[str, int]:
    """{título: id} de los proyectos que ya existen."""
    response = session.get(
        f"{base_url}/api/projects/", params={"page_size": 200}, timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("results", payload) if isinstance(payload, dict) else payload
    return {p["title"]: p["id"] for p in items}


def load_annotator(
    session: requests.Session,
    base_url: str,
    annotator: str,
    tasks_path: Path,
    config: str,
    replace: bool,
    known: dict[str, int],
) -> None:
    title = f"{PROJECT_PREFIX} — {annotator}"

    if title in known:
        if not replace:
            print(
                f"⊘ '{title}' ya existe (id={known[title]}) — no se toca.\n"
                f"    Anotar: {base_url}/projects/{known[title]}/data\n"
                "    Usa --replace para recrearlo (BORRA sus anotaciones)."
            )
            return
        session.delete(
            f"{base_url}/api/projects/{known[title]}/",
            headers=_headers(session, base_url), timeout=60,
        )
        print(f"  (proyecto anterior id={known[title]} eliminado)")

    response = session.post(
        f"{base_url}/api/projects/",
        headers=_headers(session, base_url),
        timeout=60,
        json={
            "title": title,
            "description": (
                "IdeoGraphCO — marca la CLASE DOMINANTE de cada artículo. "
                "Anota de forma independiente: no compares con el otro "
                "anotador hasta terminar (el α de Krippendorff solo es "
                "válido si la anotación del solape fue ciega)."
            ),
            "label_config": config,
        },
    )
    if response.status_code not in (200, 201):
        print(f"✗ {annotator}: no se pudo crear el proyecto "
              f"(HTTP {response.status_code}) {response.text[:200]}")
        return

    project_id = response.json()["id"]
    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    imported = session.post(
        f"{base_url}/api/projects/{project_id}/import",
        headers=_headers(session, base_url),
        json=tasks,
        timeout=300,
    )
    if imported.status_code not in (200, 201):
        print(f"✗ {annotator}: proyecto {project_id} creado pero la importación "
              f"falló (HTTP {imported.status_code}) {imported.text[:200]}")
        return

    count = imported.json().get("task_count", len(tasks))
    print(f"✓ {annotator}: {count} artículos cargados")
    print(f"    Anotar en: {base_url}/projects/{project_id}/data")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crea los proyectos de anotación en Label Studio e importa el gold set",
    )
    parser.add_argument(
        "--annotators", nargs="+", default=["anotador1", "anotador2"],
        help="Nombres usados en prepare_gold_set.py",
    )
    parser.add_argument(
        "--version", type=str, default="v2",
        help="Sufijo de versión del gold set (default: v2)",
    )
    parser.add_argument(
        "--tasks-dir", type=str, default=None,
        help="Directorio de tareas (default: annotation/labelstudio)",
    )
    parser.add_argument("--url", type=str, default="http://localhost:8080")
    parser.add_argument(
        "--user", type=str, default=os.environ.get("LABEL_STUDIO_USERNAME"),
        help="Email de tu cuenta de Label Studio (o LABEL_STUDIO_USERNAME)",
    )
    parser.add_argument(
        "--password", type=str, default=os.environ.get("LABEL_STUDIO_PASSWORD"),
        help="Contraseña (o LABEL_STUDIO_PASSWORD)",
    )
    parser.add_argument(
        "--with-scales", action="store_true",
        help="Añade los 8 ratings de intensidad 1-5 además de la clase "
             "dominante (por defecto solo la clase: 1 decisión por artículo)",
    )
    parser.add_argument(
        "--replace", action="store_true",
        help="Recrea los proyectos que ya existan. BORRA sus anotaciones.",
    )
    args = parser.parse_args()

    if not args.user or not args.password:
        raise SystemExit(
            "✗ Faltan credenciales. Pasa --user y --password, o exporta\n"
            "  LABEL_STUDIO_USERNAME y LABEL_STUDIO_PASSWORD."
        )

    base_url = args.url.rstrip("/")
    tasks_dir = (
        Path(args.tasks_dir) if args.tasks_dir
        else ROOT / "annotation" / "labelstudio"
    )
    base = f"gold_set_{args.version}"

    missing = [
        name for name in args.annotators
        if not (tasks_dir / f"{base}_{name}_tasks.json").exists()
    ]
    if missing:
        raise SystemExit(
            f"✗ No hay tareas para: {', '.join(missing)} en {tasks_dir}\n"
            "  Genera el gold set primero:\n"
            f"    python scripts/prepare_gold_set.py --annotators "
            f"{' '.join(args.annotators)} --version {args.version}"
        )

    session = login(base_url, args.user, args.password)
    known = existing_projects(session, base_url)
    config = labelstudio.build_labeling_config(with_scales=args.with_scales)

    modo = "clase dominante + escalas 1-5" if args.with_scales else "solo clase dominante"
    print(f"Label Studio: {base_url}  |  interfaz: {modo}\n")

    for annotator in args.annotators:
        load_annotator(
            session, base_url, annotator,
            tasks_dir / f"{base}_{annotator}_tasks.json",
            config, args.replace, known,
        )

    print(
        "\nCuando terminen de anotar, cada uno exporta desde su proyecto:\n"
        "  Export → JSON  (el formato completo, NO JSON-MIN)\n"
        f"  guardar como annotation/{base}_<anotador>.json\n"
        "\nY luego:\n"
        "  python scripts/ingest_gold.py --books "
        + " ".join(f"annotation/{base}_{n}.json" for n in args.annotators)
    )


if __name__ == "__main__":
    main()
