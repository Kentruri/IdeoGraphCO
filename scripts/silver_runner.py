#!/usr/bin/env python3
"""Etiqueta el silver de forma desatendida con un modelo de Claude vía `claude -p`.

Por qué haiku y no Gemini: sobre los 1.276 artículos del gold con consenso de
tres jueces, haiku coincide con ese consenso el 92,4 % de las veces y su
distribución lo calca (institucionalismo 8,9 % frente a 8,6 %; sin_encuadre
56,1 % frente a 54,8 %). Gemini, medido sobre el estrato aleatorio del mismo
plan, manda el 46,9 % a institucionalismo: reproduce el sesgo que la v1.1 del
codebook corrigió, aunque lea el codebook corregido.

Por qué `claude -p` y no la API: no hay ANTHROPIC_API_KEY; la cuota es la de
la suscripción. Reutiliza el control de cuota de `filter_runner`, que ya tiene
resueltos el reloj de pared (macOS detiene el monotónico al dormir) y la
detección de límites por forma y no por lista de frases.

    python scripts/silver_runner.py --cap-semanal 30
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.filter_runner import (  # noqa: E402
    _USAGE_LIMIT_RE,
    log,
    seconds_until_reset,
    sleep_interruptible,
    weekly_usage,
)

ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(ROOT / ".venv" / "bin" / "python")
TANDA_TIMEOUT = 5400.0          # techo por tanda, en segundos de PARED
# El CLI instalado (2.1.270) no admite `claude-opus-5-5`: pide 2.1.280+. El
# alias `opus` sí resuelve, a la versión de opus que esta build soporta. Se
# deja el alias para no actualizar el CLI con corridas en vuelo; queda anotado
# que el tercer juez no es exactamente el mismo opus de la calibración del gold.
MODELOS = {"opus": "opus", "sonnet": "claude-sonnet-5-5",
           "haiku": "claude-haiku-5-5"}

WORKDIR = VOTOS = CORPUS = None   # los fija main() según el juez
MODEL = ""
# Tokens de texto de artículo por tanda. Con 400k, opus llegaba a 330k de
# contexto y releía de caché ~88k tokens por artículo (cada turno relee todo
# lo anterior): el coste crece con el cuadrado de la tanda. 110k mantiene el
# contexto bajo ~160k y abarata opus a la mitad; haiku y sonnet ya se
# compactaban hacia los 168k, así que apenas cambian.
BUDGET = 110_000
# Modo calibración: el juez vota artículos del GOLD para medirse contra el
# humano (auditoría P1.3). Sus votos van fuera de data/silver —silver_agent
# se niega a votar el gold si no— y nunca entran al entrenamiento.
CALIB: Path | None = None


def arma_prompt() -> str:
    juez = VOTOS.stem.replace('votos_', '').rstrip('0123456789_sinenc')
    juez = next(j for j in MODELOS if VOTOS.stem.startswith(f'votos_{j}'))
    GOLD = " --allow-gold" if CALIB else ""
    NO_TOQUES = (f"No toques data/raw/ ni annotation/ salvo tu carpeta {WORKDIR}."
                 if CALIB else "No toques data/raw/ ni annotation/.")
    return f"""Etiqueta una tanda del silver set de IdeoGraphCO con la clase ideológica dominante.

Eres la tanda que acaba de lanzar `silver_runner.py` (y a este, el orquestador
de la ronda). Verás otros procesos, logs y PID en marcha: son tus compañeros,
otros jueces y otros shards, cada uno con SU carpeta y SU almacén de votos. La
carpeta {WORKDIR} y el almacén {VOTOS} son solo tuyos: nadie más escribe ahí.
No investigues el entorno —ni logs, ni PID, ni REANUDAR.md, ni el código—:
carga el criterio y ejecuta el ciclo.

Carga el criterio primero:

    Skill(skill="codebook-silver")

y el codebook canónico, que manda sobre todo lo demás:

    {PYTHON} -c "from src.agents.silver.codebook import build_system_prompt; print(build_system_prompt(include_examples=True))"

Repite este ciclo hasta que el script te diga que pares:

1. Pide el lote. En la PRIMERA llamada de esta sesión añade --reset-session;
   en las siguientes, no:

    {PYTHON} scripts/silver_agent.py next --judge {juez} \\
      --workdir {WORKDIR} --verdicts {VOTOS} \\
      --input {CORPUS} --full --size 10 --budget {BUDGET}{GOLD} --reset-session

2. Lee el lote entero. Formato: [n], titular, cuerpo. No verás la fuente: es a
   propósito, el codebook prohíbe etiquetar por el medio.

3. Decide cada artículo. Una línea por artículo: `n clase [confianza]`.
   Clases: populismo institucionalismo personalismo doctrinarismo soberanismo
   globalismo conservadurismo progresismo, más `sin_encuadre` (político pero
   ninguna de las ocho lo estructura) y `dud` (empate real, con moderación).
   No te saltes ninguno: el script rechaza los lotes incompletos.

4. Escribe las decisiones con Write en
   {WORKDIR}/decisiones_NNN.txt (mismo número que el lote).

5. Ingiere:

    {PYTHON} scripts/silver_agent.py ingest --batch N \\
      --decisions {WORKDIR}/decisiones_NNN.txt \\
      --judge {juez} --workdir {WORKDIR} --verdicts {VOTOS} \\
      --model {MODEL} --keep-batch

6. Vuelve al paso 1 SIN --reset-session.

PARA cuando `next` imprima "PRESUPUESTO DE LA TANDA AGOTADO", o antes si notas
que te queda poco contexto. Termina e ingiere siempre el lote que tengas
empezado: uno entregado sin ingerir bloquea el siguiente `next`.

No ejecutes `status`. {NO_TOQUES}
Al terminar, informa en tres líneas: lotes, artículos y reparto por clase."""


def pendientes() -> tuple[int, int]:
    """(votados, total del plan), contando solo los artículos de ESTA cola.

    El almacén de votos guarda también ids de versiones anteriores de la
    cola; contarlos todos daba "plan completo" con 907 artículos sin votar
    (2-nov: 7.460 votos para una cola de 7.422, 492 de ella sin voto).
    """
    ids = {json.loads(x)["id"] for x in CORPUS.open(encoding="utf-8") if x.strip()}
    if not VOTOS.exists():
        return 0, len(ids)
    vistos = {json.loads(x)["id"] for x in
              VOTOS.read_text(encoding="utf-8").splitlines() if x.strip()}
    return len(vistos & ids), len(ids)


def libera_lote_a_medias() -> None:
    """Un lote entregado y sin ingerir bloquea el siguiente `next`."""
    estado = WORKDIR / "state.json"
    if not estado.exists():
        return
    d = json.loads(estado.read_text(encoding="utf-8"))
    if d.get("pending_batch"):
        d["pending_batch"] = None
        d["session_tokens"] = 0
        estado.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        log("   lote a medias de la tanda anterior: liberado")


def corre_tanda(claude_bin: str) -> tuple[int, str]:
    cmd = [claude_bin, "-p", arma_prompt(), "--agent", "juez-silver", "--model", MODEL,
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Bash(*silver_agent.py*)", "Bash(*codebook*)",
           "Read", "Write", "Skill"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    except OSError as exc:
        return 1, f"no pude lanzar claude: {exc}"

    # El techo de tiempo se comprueba en el bucle principal, y la lectura va en
    # un hilo aparte: `readline()` BLOQUEA, así que leer aquí dejaba el techo
    # sin comprobar y una tanda muda seguía viva indefinidamente (pasó: haiku
    # estuvo 5 h parado en la tanda 2 sin que saltara el corte de 90 min).
    salida: list[str] = []

    def _lee() -> None:
        if proc.stdout:
            for linea in proc.stdout:
                salida.append(linea)

    hilo = threading.Thread(target=_lee, daemon=True)
    hilo.start()

    tope = datetime.now() + timedelta(seconds=TANDA_TIMEOUT)
    while proc.poll() is None:
        if datetime.now() > tope:
            proc.kill()
            hilo.join(timeout=5)
            return 124, "".join(salida) + \
                f"\n[la tanda superó el techo de {TANDA_TIMEOUT/60:.0f} min]"
        time.sleep(2)
    hilo.join(timeout=10)
    return proc.returncode or 0, "".join(salida)


def main() -> int:
    global WORKDIR, VOTOS, CORPUS, MODEL, BUDGET, CALIB
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap-semanal", type=float, default=30.0,
                    help="para al superar este %% de cuota semanal")
    ap.add_argument("--juez", default="haiku", choices=list(MODELOS))
    ap.add_argument("--corpus", default="data/silver/corpus_plan.jsonl")
    ap.add_argument("--sufijo", default="", help="distingue corridas sobre el mismo juez")
    ap.add_argument("--budget", type=int, default=BUDGET,
                    help="tokens de texto de artículo por tanda")
    ap.add_argument("--calibracion", default=None,
                    help="carpeta FUERA de data/silver: vota el gold para auditar al juez")
    args = ap.parse_args()

    BUDGET = args.budget
    CALIB = ROOT / args.calibracion if args.calibracion else None
    if CALIB and "data/silver" in str(CALIB):
        raise SystemExit("✗ La calibración vota el gold: sus votos no pueden ir a data/silver.")
    base = CALIB or ROOT / "data" / "silver"
    tag = f"{args.juez}{args.sufijo}"
    WORKDIR = base / f"agent_batches_{tag}"
    VOTOS = base / f"votos_{tag}.jsonl"
    CORPUS = ROOT / args.corpus
    MODEL = MODELOS[args.juez]

    claude_bin = shutil.which("claude")
    if not claude_bin:
        log("✗ no encuentro el binario `claude`")
        return 1
    WORKDIR.mkdir(parents=True, exist_ok=True)
    # El PID en disco es la única forma fiable de saber si este runner vive:
    # `pgrep -f` encuentra cualquier shell cuya línea de comando contenga el
    # patrón, incluida la del propio pgrep.
    pidf = base / f"runner_{tag}.pid"
    pidf.write_text(str(os.getpid()), encoding="utf-8")

    tanda = 0
    while True:
        hechos, total = pendientes()
        if hechos >= total:
            log(f"✓ plan completo: {hechos:,}/{total:,}")
            return 0

        uso = weekly_usage(claude_bin)
        if uso and uso[0] >= args.cap_semanal:
            log(f"⏹ cuota semanal al {uso[0]:.0f} %, tope {args.cap_semanal:.0f} %. "
                f"Paro con {hechos:,}/{total:,} hechos.")
            return 0

        tanda += 1
        pct = f" · semanal {uso[0]:.0f} %" if uso else ""
        log(f"▶ tanda {tanda} · {hechos:,}/{total:,}{pct}")
        libera_lote_a_medias()

        code, salida = corre_tanda(claude_bin)
        nuevos, _ = pendientes()
        log(f"   +{nuevos - hechos} artículos (code={code})")

        if _USAGE_LIMIT_RE.search(salida):
            espera = seconds_until_reset(salida) or 1800
            log(f"⏸ límite de sesión. Espero {espera/60:.0f} min.")
            sleep_interruptible(espera + 60, "esperando el reinicio de sesión")
            continue
        if nuevos == hechos:
            log("   la tanda no avanzó: espero 5 min y reintento")
            sleep_interruptible(300, "sin avance")


if __name__ == "__main__":
    raise SystemExit(main())
