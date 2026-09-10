"""Bucle desatendido del filtrado: invoca al agente tanda tras tanda.

El agente `filtro-politico` vive dentro de una sesión de Claude Code, así que
no puede ser un proceso de launchd por sí mismo. Lo que sí lo es: `claude -p`,
que corre una sesión headless y termina. Cada invocación procesa UNA tanda
(hasta agotar su presupuesto de contexto) y sale; el cursor persistente hace
que la siguiente continúe exactamente donde quedó.

Está en Python y no en bash a propósito: launchd no le concede a /bin/bash
acceso al Escritorio (TCC de macOS) y el servicio moría con "Operation not
permitted", mientras que el intérprete del venv sí lo tiene concedido.

Se detiene solo cuando: termina el corpus, o varias tandas seguidas no
avanzan nada (señal de que algo va mal y seguir solo quemaría cuota).
"""

import json
import os
import shutil
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PYTHON = str(ROOT / ".venv" / "bin" / "python")
AGENT_FILTER = str(ROOT / "scripts" / "agent_filter.py")

MODEL = os.environ.get("FILTER_MODEL", "opus")
COOLDOWN = float(os.environ.get("FILTER_COOLDOWN", "60"))
# Techo por tanda: si una invocación se cuelga, no debe bloquear el servicio
# para siempre. Al matarla, el cursor deja el lote a medias sin ingerir y la
# siguiente tanda lo rehace.
TANDA_TIMEOUT = float(os.environ.get("FILTER_TANDA_TIMEOUT", "5400"))
# Cada cuánto el log dice que sigue vivo mientras el agente trabaja.
HEARTBEAT = float(os.environ.get("FILTER_HEARTBEAT", "120"))

PROMPT = """Procesa una tanda completa del corpus de IdeoGraphCO aplicando la skill codebook-filtro.

Trabaja así, repitiendo el ciclo hasta que el script te diga que pares:

1. Pide el lote:
     .venv/bin/python scripts/agent_filter.py next --reset-session
   (--reset-session SOLO en esta primera llamada; en las siguientes, sin él)

2. Lee el lote completo con Read. Formato: "[n] fuente", titular, cuerpo.

3. Decide CADA artículo aplicando el codebook. Una línea por artículo:
     n categoria [confianza] [marcas]
   Categorias: pol for non bio gar dud
   Marcas: br dg tr pw
   No te saltes ninguno. Piensa cada caso: el cuerpo es donde se ve si un
   comunicado defiende una politica publica o solo anuncia un horario de
   atencion. Recuerda que el criterio es PERMISIVO en politicidad (la opinion
   politica, el debate de politica sectorial y la memoria historica con
   lectura politica ENTRAN) y ESTRICTO en colombianidad.
   Usa dud solo en el caso limite real, no para evitar pronunciarte.

4. Escribe las decisiones con Write en data/agent_batches/decisiones_NNN.txt
   (NNN = el numero del lote, con tres digitos).

5. Ingiere:
     .venv/bin/python scripts/agent_filter.py ingest --batch N --decisions data/agent_batches/decisiones_NNN.txt

6. Vuelve al paso 1 SIN --reset-session.

PARA cuando next imprima "PRESUPUESTO DE LA TANDA AGOTADO", o antes si notas
que te queda poco contexto. Termina e ingiere siempre el lote que tengas
empezado: un lote entregado y sin ingerir bloquea el siguiente next.

Al cerrar informa de: lotes y articulos procesados, cuantos conservaste, el
cursor y el porcentaje exactos, que resolvio Gemini en los dud, y cualquier
patron que hayas visto (fuentes que solo dan paginas estaticas, restos de
plantilla recurrentes, tipos de articulo que el codebook no cubre bien)."""

# Hay que separar dos cosas que "parecen lo mismo" y piden esperas muy
# distintas. El límite de uso se renueva en ventanas de ~5 h: reintentar cada
# 30 min contra él son 9 intentos fallidos que no adelantan nada. Una
# sobrecarga pasajera, en cambio, se pasa en minutos, y esperar 5 h por ella
# tira media jornada de trabajo.
# Una lista de frases literales falla en cuanto el producto cambia el texto:
# "session limit" no casaba con "usage limit" ni con "limit reached", y el
# bucle pasó media hora martilleando el límite en lugar de dormir. Se usa un
# patrón sobre la FORMA del mensaje, más un disparador aparte: si anuncia una
# hora de renovación, es un límite, diga lo que diga el resto.
_USAGE_LIMIT_RE = re.compile(
    r"(?:session|usage|weekly|hourly|daily|\d+\s*-?\s*hour)\s+limit"
    r"|limit\s+reached"
    r"|hit\s+your\s+\w+\s+limit"
    r"|out\s+of\s+(?:credits?|quota)"
    r"|quota|credit\s+balance|insufficient\s+credit|upgrade\s+to\s+increase",
    re.IGNORECASE,
)
TRANSIENT_MARKERS = ("overloaded", "rate limit", "too many requests",
                     "503", "529", "connection", "timeout")

# Espera cuando el límite de uso no dice cuándo se renueva.
DEFAULT_USAGE_WAIT = float(os.environ.get("FILTER_QUOTA_WAIT", str(4.5 * 3600)))
TRANSIENT_WAIT = float(os.environ.get("FILTER_TRANSIENT_WAIT", "300"))
# Techo del retroceso ante fallos que no sabemos clasificar.
MAX_BACKOFF = float(os.environ.get("FILTER_MAX_BACKOFF", "1800"))

_RESET_RE = re.compile(
    r"reset[s]?\s*(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)


def seconds_until_reset(output: str) -> float | None:
    """Segundos hasta la hora de renovación que anuncie el mensaje, si la hay.

    Claude Code suele decir «resets 8pm» o «limit will reset at 3:00 PM».
    Aprovecharlo evita dormir 4,5 h cuando faltaban 20 min — y evita despertar
    demasiado pronto cuando faltaban 5 h.
    """
    match = _RESET_RE.search(output)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower()
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:                      # ya pasó hoy → es de mañana
        target += timedelta(days=1)
    # Un margen pequeño: despertar justo en el segundo del corte suele volver
    # a chocar con el límite.
    delta = (target - now).total_seconds() + 120
    return delta if delta <= 24 * 3600 else None


def sleep_interruptible(seconds: float, note: str,
                       may_sleep_machine: bool = False) -> None:
    """Duerme en tramos para que una señal de parada se atienda al momento.

    `time.sleep` reanuda el resto del plazo tras ejecutar el manejador de
    señal: con esperas de horas, `filter_service.sh stop` se quedaría
    colgado hasta que launchd matase el proceso a lo bruto.
    """
    wake = datetime.now() + timedelta(seconds=seconds)
    stamp = f"{wake:%H:%M}" if seconds < 20 * 3600 else f"{wake:%d/%m %H:%M}"
    log(f"   ⏳ {note}. Reanudo ~{stamp} ({seconds / 3600:.1f} h).")

    # Soltar `caffeinate` SOLO cuando el llamador lo autoriza explícitamente.
    # Antes se soltaba en toda espera de más de una hora, y eso incluía la del
    # límite de SESIÓN (1-5 h): el Mac se dormía, y como nadie lo despertaba,
    # el trabajo no se reanudaba a la hora anunciada. La única espera que
    # justifica dejar dormir el equipo es la SEMANAL, que puede durar días.
    if may_sleep_machine:
        caffeinate(False)
        log("      (caffeinate liberado: el Mac puede dormir mientras espera)")
    else:
        caffeinate(True)
        log("      (el Mac se mantiene despierto para reanudar solo)")

    # Plazo ABSOLUTO, no cuenta atrás: si la máquina se suspende, un contador
    # que resta 60 por vuelta pierde el tiempo real transcurrido y despierta
    # tarde. Con una hora objetivo, al volver de la suspensión sabe si ya toca.
    deadline = datetime.now() + timedelta(seconds=seconds)
    while not _stop and datetime.now() < deadline:
        restante = (deadline - datetime.now()).total_seconds()
        time.sleep(max(1.0, min(60.0, restante)))
    caffeinate(True)


# Umbral del límite SEMANAL en el que el servicio deja de consumir. La idea
# es reservarle al usuario el resto de la semana para su propio trabajo.
WEEKLY_STOP_PCT = float(os.environ.get("FILTER_WEEKLY_STOP_PCT", "80"))

# Mínimo de artículos FILTRADOS que debe tener el corpus. Si al terminar
# de decidir no se alcanza, el servicio arranca el scraping para traer
# más materia prima y sigue filtrando lo que llegue.
MIN_CORPUS = int(os.environ.get("FILTER_MIN_CORPUS", "40000"))
# Crudos que se piden al colector cuando hay que reponer. 0 = calcularlo
# a partir de lo que falte para MIN_CORPUS.
COLLECT_EXTRA = int(os.environ.get("FILTER_COLLECT_EXTRA", "0"))
COLLECT_POLL = float(os.environ.get("FILTER_COLLECT_POLL", "1800"))
MAX_STALE_COLLECTS = int(os.environ.get("FILTER_MAX_STALE_COLLECTS", "4"))
# Dos límites distintos, dos reacciones distintas. Meterlos en un solo
# interruptor obligaba a elegir entre parar demasiado pronto (al primer
# corte de sesión) o dormir días con el proceso vivo.
#
#   sesión (se renueva en horas)  → por defecto ESPERA y sigue
#   semanal (se renueva en días)  → por defecto PARA
STOP_ON_SESSION_LIMIT = os.environ.get(
    # nombre viejo aceptado por compatibilidad con plists ya instalados
    "FILTER_STOP_ON_SESSION_LIMIT",
    os.environ.get("FILTER_STOP_ON_LIMIT", ""),
) not in ("", "0")
WEEKLY_WAIT = os.environ.get("FILTER_WEEKLY_WAIT", "") not in ("", "0")

# `claude -p "/usage"` se resuelve en el cliente: 0 turnos, 0 tokens, coste 0.
# Por eso se puede consultar antes de cada tanda sin gastar nada de cuota.
_WEEKLY_RE = re.compile(
    r"current week \(all models\):\s*(\d+(?:\.\d+)?)\s*%\s*used"
    r"(?:.*?resets\s+(.+?)(?:\s*\(|$))?",
    re.IGNORECASE,
)
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}


def parse_weekly_usage(text: str) -> tuple[float, datetime | None] | None:
    """Extrae («% semanal usado», «cuándo se renueva») de la salida de /usage.

    Devuelve None si no se reconoce nada: el llamador decide qué hacer, y la
    decisión es seguir trabajando. Un fallo al leer el porcentaje no debe
    parar días de trabajo — el tope de sesión sigue protegiendo aparte.
    """
    match = _WEEKLY_RE.search(text)
    if not match:
        return None
    pct = float(match.group(1))
    return pct, _parse_reset_date(match.group(2) or "")


def _parse_reset_date(raw: str) -> datetime | None:
    """«Sep 7 at 4pm» / «Sep 7 at 4:30pm» → datetime local."""
    m = re.search(r"([A-Za-z]{3})\w*\s+(\d{1,2})\s+at\s+"
                  r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", raw, re.IGNORECASE)
    if not m:
        return None
    month = _MONTHS.get(m.group(1).lower())
    if not month:
        return None
    day, hour = int(m.group(2)), int(m.group(3))
    minute = int(m.group(4) or 0)
    meridiem = (m.group(5) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    now = datetime.now()
    year = now.year
    try:
        target = datetime(year, month, day, hour, minute)
    except ValueError:
        return None
    if target < now - timedelta(days=180):   # cruce de año
        target = target.replace(year=year + 1)
    return target


def weekly_usage(claude_bin: str) -> tuple[float, datetime | None] | None:
    try:
        result = subprocess.run(
            [claude_bin, "-p", "/usage", "--model", "sonnet"],
            capture_output=True, text=True, cwd=ROOT, timeout=180,
        )
    except Exception as exc:
        log(f"   ⚠ no pude consultar /usage ({type(exc).__name__})")
        return None
    return parse_weekly_usage(result.stdout or "")


_stop = False
_caffeinate = None
_last_total = None
_stale_collect = 0


def _handle_term(*_):
    global _stop
    _stop = True
    log("recibida señal de parada: termino tras la tanda en curso")


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def status() -> dict:
    try:
        out = subprocess.run(
            [PYTHON, AGENT_FILTER, "status", "--json"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        return json.loads(out.stdout)
    except Exception as exc:
        log(f"✗ no puedo leer el estado ({type(exc).__name__})")
        return {}


def build_corpus(verbose: bool = True) -> int:
    """Materializa el corpus y devuelve cuántos artículos quedaron dentro.

    El número sale de la propia salida de `build` ("✓ N artículos → …"), que
    es la cuenta de lo REALMENTE escrito con la precedencia de motores
    aplicada — no la del log de decisiones, que puede diferir.
    """
    out = subprocess.run([PYTHON, AGENT_FILTER, "build"],
                         capture_output=True, text=True, cwd=ROOT, timeout=600)
    salida = out.stdout or ""
    if verbose:
        for line in salida.splitlines():
            log(f"   ├ {line}")
    m = re.search(r"✓\s*([\d,\.]+)\s+artículos", salida)
    if m:
        return int(m.group(1).replace(",", "").replace(".", ""))
    return status().get("kept", 0)


def should_finish(kept: int, collector_active: bool) -> bool:
    """¿Se puede dar por cerrado el corpus?

    Dos condiciones, y la segunda es la que se olvidó al principio: el filtro
    (~1.800/h) adelanta al colector (~700/h), así que alcanzaba el mínimo con
    el scraping a medias, se declaraba terminado y se apagaba dejando miles
    de artículos recién recogidos sin decidir. Si se está scrapeando es
    porque se quiere ese material DENTRO del corpus.
    """
    return kept >= MIN_CORPUS and not collector_active


def raw_needed(kept: int, decided: int, total: int, objetivo: int) -> int:
    """Cuántos artículos CRUDOS más hacen falta para llegar al objetivo.

    El filtro conserva algo más de la mitad, así que pedirle al colector la
    diferencia en bruto se quedaría corto: hay que dividir por la tasa de
    conservación medida sobre lo ya decidido.
    """
    tasa = kept / decided if decided else 0.5
    tasa = max(tasa, 0.05)          # nunca dividir por ~0 y pedir un absurdo
    # Lo ya scrapeado y aún sin decidir también aportará: descontarlo evita
    # mandar al colector a por miles de artículos que no hacían falta.
    pendiente_aporta = max(0, total - decided) * tasa
    faltan = objetivo - kept - pendiente_aporta
    return max(0, int(faltan / tasa))


def collector_running() -> bool:
    out = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/com.ideographco.collector"],
        capture_output=True, text=True)
    return "state = running" in out.stdout


def start_collector(state: dict, kept: int) -> bool:
    """Arranca el colector pidiéndole el crudo que falta. False si no aporta.

    Devuelve False cuando el colector ya corrió y el JSONL no creció: eso
    significa que las fuentes están agotadas y seguir esperando sería
    quedarse dormido para siempre.
    """
    global _last_total, _stale_collect
    total = state["total"]
    if _last_total is not None and total <= _last_total:
        _stale_collect += 1
        log(f"   el corpus crudo sigue en {total:,} "
            f"({_stale_collect}/{MAX_STALE_COLLECTS} comprobaciones sin crecer)")
        if _stale_collect >= MAX_STALE_COLLECTS:
            return False
    else:
        _stale_collect = 0
    _last_total = total

    if collector_running():
        log("   el colector ya está recolectando")
        return True

    # Con COLLECT_EXTRA se pide una cantidad FIJA de crudos en vez de la
    # calculada a partir del déficit: es una decisión del usuario sobre el
    # tamaño del corpus, no algo que deba deducir de la tasa de conservación.
    extra = COLLECT_EXTRA or raw_needed(kept, state["decided"], total, MIN_CORPUS)
    objetivo = total + extra
    log(f"▶ arranco el scraping hacia {objetivo:,} crudos "
        f"(para llegar a {MIN_CORPUS:,} filtrados)")
    collector = str(ROOT / "scripts" / "collector.sh")
    for args in (["install", "--target", str(objetivo), "--no-filter",
                  "--per-round", "40", "--workers", "12"], ["start"]):
        result = subprocess.run(["/bin/bash", collector, *args],
                                capture_output=True, text=True, cwd=ROOT,
                                timeout=300)
        if result.returncode != 0:
            log(f"   ✗ collector.sh {args[0]} falló: "
                f"{(result.stderr or result.stdout)[:200]}")
            return False
    return True


def caffeinate(on: bool) -> None:
    """Mantiene el Mac despierto SOLO mientras se trabaja.

    Antes `caffeinate` envolvía al runner entero, así que una espera larga
    (el límite semanal puede tardar días en renovarse) dejaba el equipo
    encendido sin hacer nada. Ahora se suelta durante las esperas largas.
    """
    global _caffeinate
    if on:
        if _caffeinate is None or _caffeinate.poll() is not None:
            _caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-is"])
    elif _caffeinate is not None and _caffeinate.poll() is None:
        _caffeinate.terminate()
        _caffeinate = None


def release_stale_batch() -> None:
    """Libera un lote entregado y sin ingerir de una sesión anterior.

    Cualquier parada dura (pausa del servicio, cierre de sesión, tanda que
    supera su techo) deja el lote en curso marcado como pendiente, y el
    siguiente `next` se niega a entregar otro. Sin esto, reanudar exigía
    intervención manual: el servicio arrancaba y se quedaba dando vueltas
    sin avanzar. Los artículos no se pierden — vuelven a salir en el
    siguiente lote.
    """
    state_path = ROOT / "data" / "agent_batches" / "filter_state.json"
    if not state_path.exists():
        return
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    pending = state.get("pending_batch")
    if not pending:
        return
    for suffix in (".txt", ".manifest.json"):
        (state_path.parent / f"lote_{pending:03d}{suffix}").unlink(missing_ok=True)
    # También el archivo de decisiones, si el agente llegó a escribirlo: sin
    # manifiesto ya no se puede ingerir, y esos artículos se vuelven a servir
    # en el siguiente lote. Dejarlo solo acumulaba huérfanos que parecían
    # trabajo pendiente.
    (state_path.parent / f"decisiones_{pending:03d}.txt").unlink(missing_ok=True)
    state["pending_batch"] = None
    state["session_tokens"] = 0
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    log(f"   lote {pending} quedó a medias en la sesión anterior: liberado "
        "(esos artículos vuelven a salir)")


def run_tanda(claude_bin: str) -> tuple[int, str]:
    # Sin TTY, cualquier diálogo de permisos colgaría el servicio para
    # siempre: las herramientas van explícitamente permitidas y acotadas.
    cmd = [
        claude_bin, "-p", PROMPT,
        "--agent", "filtro-politico",
        "--model", MODEL,
        "--permission-mode", "acceptEdits",
        "--allowedTools", "Bash(*agent_filter.py*)", "Read", "Write", "Skill",
    ]
    # Se lanza con Popen y se sondea, en vez de esperar callado a que termine:
    # una tanda dura ~11 min y con `subprocess.run` el log no escribía nada en
    # todo ese rato, así que desde fuera era indistinguible de estar pausado.
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, cwd=ROOT)
    except OSError as exc:
        return 1, f"no pude lanzar claude: {exc}"

    deadline = time.monotonic() + TANDA_TIMEOUT
    last_beat = time.monotonic()
    while proc.poll() is None:
        time.sleep(2)
        if time.monotonic() - last_beat >= HEARTBEAT:
            last_beat = time.monotonic()
            snapshot = status()
            if snapshot:
                log(f"   · trabajando… {snapshot['decided']:,} decididos "
                    f"({snapshot['pct']:.2f}%) · lote {snapshot['batch_seq'] - 1}")
        if time.monotonic() > deadline:
            proc.kill()
            proc.wait(timeout=30)
            return 124, f"la tanda superó el techo de {TANDA_TIMEOUT / 60:.0f} min"

    output = proc.stdout.read() if proc.stdout else ""
    return proc.returncode, output


def main() -> int:
    signal.signal(signal.SIGTERM, _handle_term)
    signal.signal(signal.SIGINT, _handle_term)

    claude_bin = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not claude_bin or not Path(claude_bin).exists():
        log("✗ no encuentro el binario 'claude'. Define CLAUDE_BIN.")
        return 1

    log(f"═══ arranca el filtrado desatendido (modelo: {MODEL}) ═══")
    log(f"    tope del límite semanal: {WEEKLY_STOP_PCT:.0f}%")
    caffeinate(True)
    release_stale_batch()
    stalls = 0
    tanda = 0
    quota_waits = 0

    while not _stop:
        state = status()
        if not state:
            return 1
        if state["remaining"] == 0:
            kept = build_corpus(verbose=False)
            # No dar por terminado mientras el colector siga trayendo cosas:
            # el filtro va más rápido que el scraping, así que alcanzaría el
            # mínimo con el colector a medias y se apagaría dejando miles de
            # artículos recién recogidos sin decidir. Si se está scrapeando,
            # es porque se quiere ese material DENTRO del corpus.
            recolectando = collector_running()
            if kept >= MIN_CORPUS and recolectando:
                log(f"   {kept:,} filtrados (mínimo {MIN_CORPUS:,} ya "
                    "alcanzado), pero el colector sigue trayendo: no cierro "
                    "hasta que termine.")
                sleep_interruptible(COLLECT_POLL, "esperando más materia prima")
                continue

            if should_finish(kept, recolectando):
                caffeinate(False)
                build_corpus()
                log(f"✓ CORPUS COMPLETO: {kept:,} artículos filtrados "
                    f"(objetivo {MIN_CORPUS:,}).")
                log("  El corpus filtrado está en data/raw/articles.jsonl")
                log("  Siguiente: .venv/bin/python scripts/label.py   # silver")
                return 0

            # Se acabó lo que había que decidir, pero el corpus filtrado no
            # llega al mínimo. Solo un ~54% de lo crudo sobrevive al filtro,
            # así que la única salida es traer más materia prima.
            log(f"⚠ Todo decidido, pero solo {kept:,} de {MIN_CORPUS:,} "
                "artículos filtrados.")
            if not start_collector(state, kept):
                caffeinate(False)
                log("✗ El scraping no está aportando artículos nuevos: las "
                    "fuentes dieron lo que tenían.")
                log(f"  Corpus final: {kept:,} artículos. Para subir de ahí "
                    "hacen falta fuentes nuevas o esperar a que publiquen.")
                return 0
            # El colector escribe en el MISMO JSONL, así que la vuelta
            # siguiente ve un `total` mayor y sigue filtrando sin más.
            sleep_interruptible(COLLECT_POLL, "recolectando materia prima")
            continue

        # Puerta del límite SEMANAL: se comprueba ANTES de arrancar la tanda,
        # porque comprobarlo después ya habría gastado lo que se quería
        # reservar. Consultarlo no cuesta cuota (0 turnos, 0 tokens).
        weekly = weekly_usage(claude_bin)
        if weekly is None:
            log("   ⚠ /usage ilegible: sigo trabajando (la puerta semanal "
                "queda sin efecto en esta vuelta)")
        else:
            pct, resets = weekly
            if pct >= WEEKLY_STOP_PCT:
                if resets:
                    wait = (resets - datetime.now()).total_seconds() + 300
                else:
                    wait = 6 * 3600
                log(f"🛑 LÍMITE SEMANAL AL {pct:.0f}% (tope {WEEKLY_STOP_PCT:.0f}%). "
                    "Dejo de consumir para que te quede semana.")
                if WEEKLY_WAIT and wait > 0:
                    sleep_interruptible(
                        wait, "espero a que renueve la semana",
                        may_sleep_machine=True)
                    continue
                caffeinate(False)
                cuando = f" Renueva {resets:%d/%m %H:%M}." if resets else ""
                log(f"   corpus filtrado: {build_corpus(verbose=False):,}"
                    f" artículos.{cuando}")
                log("   retomar: ./scripts/filter_service.sh start")
                return 0     # 0 a propósito: KeepAlive no debe resucitarlo
            elif pct >= WEEKLY_STOP_PCT - 10:
                log(f"   semanal al {pct:.0f}% (paro al {WEEKLY_STOP_PCT:.0f}%)")

        tanda += 1
        before = state["decided"]
        log(f"── tanda {tanda} · {before:,} decididos · "
            f"faltan {state['remaining']:,} ({state['pct']:.2f}%)")

        code, output = run_tanda(claude_bin)
        gained = status().get("decided", before) - before
        log(f"   tanda {tanda} terminó (exit={code}) · +{gained} artículos")
        for line in output.strip().splitlines()[-20:]:
            log(f"   │ {line}")

        if gained > 0:
            quota_waits = 0
            # No hace falta construir aquí: `ingest` regenera el corpus tras
            # CADA lote, así que el archivo ya está al día.
            stalls = 0
            time.sleep(COOLDOWN)
            continue

        low = output.lower()
        reset_in = seconds_until_reset(output)
        # Que el mensaje anuncie renovación ES la señal más fiable de límite:
        # nada más en esta tubería dice "resets a las 9:10pm".
        if reset_in is not None or _USAGE_LIMIT_RE.search(output):
            # Un límite de uso NO es motivo para rendirse: se renueva solo.
            # El servicio duerme hasta entonces y sigue, las veces que haga
            # falta. Solo se detiene si terminó el corpus o si se le pide.
            if STOP_ON_SESSION_LIMIT:
                caffeinate(False)
                kept = build_corpus(verbose=False)
                cuando = (f" Renueva ~{datetime.now() + timedelta(seconds=reset_in):%H:%M}."
                          if reset_in else "")
                log(f"⏹ CUOTA AGOTADA y se pidió parar en ese punto.{cuando}")
                log(f"   corpus filtrado: {kept:,} artículos")
                log("   retomar: ./scripts/filter_service.sh start")
                return 0     # 0 a propósito: KeepAlive no debe resucitarlo
            quota_waits += 1
            note = (f"límite de uso; renovación anunciada (espera nº "
                    f"{quota_waits})" if reset_in
                    else f"límite de uso, sin hora anunciada (espera nº "
                         f"{quota_waits})")
            sleep_interruptible(reset_in or DEFAULT_USAGE_WAIT, note)
            continue

        if any(marker in low for marker in TRANSIENT_MARKERS):
            # Pasajero: minutos, no horas. No cuenta como tanda fallida.
            sleep_interruptible(TRANSIENT_WAIT, "sobrecarga pasajera")
            continue

        stalls += 1
        # Retroceso exponencial en vez de rendirse: si el fallo era pasajero
        # se recupera solo, y si es persistente sondea cada media hora en vez
        # de cada minuto. Salir con código de error solo conseguía que
        # launchd lo relanzase contra la misma pared.
        backoff = min(COOLDOWN * (2 ** (stalls - 1)), MAX_BACKOFF)
        log(f"   ⚠ tanda sin avance ({stalls}). Últimas líneas arriba.")
        sleep_interruptible(backoff, f"reintento con retroceso ({stalls})")

    log("⏸  detenido por señal.")
    caffeinate(False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
