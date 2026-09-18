"""Anotación del gold set: monta el proyecto y saca el resultado.

Pensado para que el anotador no tenga que tocar la interfaz más que para
etiquetar. Dos comandos:

    python scripts/anotar.py init      # crea el proyecto e importa los artículos
    python scripts/anotar.py export    # saca lo anotado a annotation/

Funciona igual en macOS, Linux y Windows: solo Python y `requests`, sin
dependencias del sistema.

Las credenciales son las de TU Label Studio local (las creas al abrirlo por
primera vez), no las de ninguna cuenta del proyecto.
"""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TASKS_DIR = ROOT / "annotation" / "labelstudio"
OUT_DIR = ROOT / "annotation"
DEFAULT_URL = "http://localhost:8080"


def _session(base_url: str, email: str, password: str):
    import requests

    s = requests.Session()
    try:
        s.get(f"{base_url}/user/login/", timeout=20)
    except requests.RequestException as exc:
        raise SystemExit(
            f"X No responde Label Studio en {base_url} ({type(exc).__name__}).\n"
            "  Arrancalo en otra terminal y dejalo abierto:\n"
            "    label-studio start --port 8080"
        ) from exc
    s.post(f"{base_url}/user/login/",
           data={"email": email, "password": password,
                 "csrfmiddlewaretoken": s.cookies.get("csrftoken")},
           headers={"Referer": f"{base_url}/user/login/"}, timeout=40)
    # Label Studio devuelve 200 con el formulario otra vez si las credenciales
    # fallan, en vez de un 4xx: lo que delata el fallo es que no haya sesion.
    if not s.cookies.get("sessionid"):
        raise SystemExit(
            f"X Usuario o contrasena incorrectos para {email}.\n"
            f"  Son los que creaste al abrir {base_url} por primera vez.")
    return s


def _headers(s, base_url: str) -> dict:
    h = {"Referer": base_url, "Content-Type": "application/json"}
    csrf = s.cookies.get("csrftoken")
    if csrf:
        h["X-CSRFToken"] = csrf
    return h


def _find_project(s, base_url: str, title: str):
    r = s.get(f"{base_url}/api/projects/", params={"page_size": 200}, timeout=40)
    r.raise_for_status()
    payload = r.json()
    items = payload.get("results", payload) if isinstance(payload, dict) else payload
    for p in items:
        if p["title"] == title:
            return p["id"]
    return None


def cmd_init(args: argparse.Namespace) -> None:
    tasks_path = TASKS_DIR / f"gold_set_{args.version}_{args.annotator}_tasks.json"
    config_path = TASKS_DIR / "labeling_config.xml"
    for p in (tasks_path, config_path):
        if not p.exists():
            raise SystemExit(f"X No existe {p}\n  Haz `git pull` primero.")

    tasks = json.loads(tasks_path.read_text(encoding="utf-8"))
    config = config_path.read_text(encoding="utf-8")
    title = f"Gold set — {args.annotator}"

    s = _session(args.url, args.user, args.password)
    existing = _find_project(s, args.url, title)
    if existing is not None and not args.replace:
        print(f"! El proyecto '{title}' ya existe (id={existing}).")
        print(f"  Anota en: {args.url}/projects/{existing}/data")
        print("  Para rehacerlo desde cero (BORRA lo anotado): --replace")
        return
    if existing is not None:
        s.delete(f"{args.url}/api/projects/{existing}/",
                 headers=_headers(s, args.url), timeout=60)
        print(f"  (proyecto anterior id={existing} eliminado)")

    r = s.post(f"{args.url}/api/projects/",
               data=json.dumps({"title": title, "label_config": config}),
               headers=_headers(s, args.url), timeout=60)
    r.raise_for_status()
    pid = r.json()["id"]

    # En bloques: un POST con 1.300 articulos completos supera el limite de
    # tamano de peticion por defecto y falla con un 413 poco explicativo.
    total = 0
    for i in range(0, len(tasks), 200):
        lote = tasks[i:i + 200]
        rr = s.post(f"{args.url}/api/projects/{pid}/import",
                    data=json.dumps(lote), headers=_headers(s, args.url),
                    timeout=300)
        rr.raise_for_status()
        total += len(lote)
        print(f"  importados {total:,}/{len(tasks):,}", flush=True)

    print(f"\nOK Proyecto listo: {total:,} articulos")
    print(f"   Anota en: {args.url}/projects/{pid}/data")


def cmd_export(args: argparse.Namespace) -> None:
    title = f"Gold set — {args.annotator}"
    s = _session(args.url, args.user, args.password)
    pid = _find_project(s, args.url, title)
    if pid is None:
        raise SystemExit(f"X No existe el proyecto '{title}'. Corre `init` primero.")

    r = s.get(f"{args.url}/api/projects/{pid}/export",
              params={"exportType": "JSON"}, timeout=600)
    r.raise_for_status()
    data = r.json()

    anotados = sum(1 for t in data
                   if [a for a in t.get("annotations", []) if not a.get("was_cancelled")])
    out = OUT_DIR / f"gold_set_{args.version}_{args.annotator}.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    # El export solo devuelve lo ANOTADO, asi que len(data) no es el total del
    # proyecto: hay que preguntarlo aparte para que el avance signifique algo.
    info = s.get(f"{args.url}/api/projects/{pid}/", timeout=40).json()
    total = info.get("task_number") or len(data)

    print(f"OK {out.relative_to(ROOT)}")
    print(f"   {anotados:,} de {total:,} articulos anotados "
          f"({100 * anotados / total:.1f}%) · faltan {total - anotados:,}")
    print("\n   Subelo al repositorio:")
    print(f"     git add {out.relative_to(ROOT)}")
    print(f'     git commit -m "gold: {args.annotator} +{anotados} articulos"')
    print("     git push")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Monta el proyecto de anotacion y saca el resultado")
    parser.add_argument("comando", choices=["init", "export"])
    parser.add_argument("--annotator", default="juan")
    parser.add_argument("--version", default="v2")
    parser.add_argument("--url", default=os.environ.get("LABEL_STUDIO_URL", DEFAULT_URL))
    parser.add_argument("--user", default=os.environ.get("LABEL_STUDIO_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("LABEL_STUDIO_PASSWORD"))
    parser.add_argument("--replace", action="store_true",
                        help="Rehacer el proyecto desde cero (BORRA lo anotado)")
    args = parser.parse_args()

    if not args.user:
        args.user = input("Correo de tu Label Studio: ").strip()
    if not args.password:
        # getpass evita que la clave quede en el historial del shell.
        args.password = getpass.getpass("Contrasena: ")

    {"init": cmd_init, "export": cmd_export}[args.comando](args)


if __name__ == "__main__":
    main()
