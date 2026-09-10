"""Relevo entre proveedores y puente con el agente (sin tocar ninguna API)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from src.scraper.llm_providers import (
    FilterProvider,
    ProviderChain,
    QuotaExhausted,
    TransientError,
)

ROOT = Path(__file__).resolve().parent.parent


def _load_agent_filter():
    """Carga scripts/agent_filter.py como módulo (no es un paquete)."""
    spec = importlib.util.spec_from_file_location(
        "agent_filter", ROOT / "scripts" / "agent_filter.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_filter"] = module
    spec.loader.exec_module(module)
    return module


class FakeProvider(FilterProvider):
    """Proveedor de prueba con una secuencia guionizada de respuestas."""

    def __init__(self, name, script, interval=0.0):
        super().__init__(client=None, model=f"{name}-model",
                         escalate_model=f"{name}-big", min_interval=interval)
        self.name = name
        self.script = list(script)
        self.calls = []

    def complete(self, system, user, schema, max_tokens, escalated=False):
        self.calls.append(escalated)
        outcome = self.script.pop(0) if self.script else "ok"
        if isinstance(outcome, Exception):
            raise outcome
        return json.dumps({"category": "political_article", "by": self.name})


def test_chain_uses_first_provider_while_it_works():
    primary = FakeProvider("gemini", ["ok"])
    backup = FakeProvider("claude", ["ok"])
    chain = ProviderChain([primary, backup])

    text, name = chain.call("sys", "hola", {}, 512)

    assert name == "gemini"
    assert json.loads(text)["by"] == "gemini"
    assert backup.calls == [], "el de relevo no debe tocarse si el primero sirve"


def test_chain_relays_to_backup_when_credits_run_out():
    primary = FakeProvider("gemini", [QuotaExhausted("credit balance too low")])
    backup = FakeProvider("claude", ["ok"])
    chain = ProviderChain([primary, backup])

    text, name = chain.call("sys", "hola", {}, 512)

    assert name == "claude"
    assert json.loads(text)["by"] == "claude"
    assert chain.exhausted() == ["gemini"]
    assert chain.active().name == "claude"


def test_exhausted_provider_is_not_retried_on_later_calls():
    # Reintentar al agotado en cada artículo re-gastaría el tiempo muerto que
    # motivó el relevo: una vez fuera, se queda fuera durante la corrida.
    primary = FakeProvider("gemini", [QuotaExhausted("quota")])
    backup = FakeProvider("claude", ["ok", "ok", "ok"])
    chain = ProviderChain([primary, backup])

    for _ in range(3):
        _, name = chain.call("sys", "hola", {}, 512)
        assert name == "claude"
    assert len(primary.calls) == 1


def test_transient_errors_retry_the_same_provider(monkeypatch):
    monkeypatch.setattr("src.scraper.llm_providers.time.sleep", lambda _: None)
    primary = FakeProvider("gemini", [TransientError("503 overloaded"), "ok"])
    backup = FakeProvider("claude", ["ok"])
    chain = ProviderChain([primary, backup])

    _, name = chain.call("sys", "hola", {}, 512)

    assert name == "gemini", "un 503 es pasajero, no motivo de relevo"
    assert backup.calls == []


def test_sustained_rate_limit_counts_as_exhausted(monkeypatch):
    monkeypatch.setattr("src.scraper.llm_providers.time.sleep", lambda _: None)
    primary = FakeProvider("gemini", [TransientError("429 rate limit")] * 9)
    backup = FakeProvider("claude", ["ok"])
    chain = ProviderChain([primary, backup], quota_streak=3, max_retries=3)

    _, name = chain.call("sys", "hola", {}, 512)

    assert name == "claude"
    assert chain.exhausted() == ["gemini"]


def test_chain_returns_none_when_everyone_is_out():
    chain = ProviderChain([FakeProvider("gemini", [QuotaExhausted("q")])])
    assert chain.call("sys", "hola", {}, 512) == (None, None)
    assert chain.active() is None


def test_min_interval_follows_the_active_provider():
    chain = ProviderChain([
        FakeProvider("gemini", [QuotaExhausted("q")], interval=4.5),
        FakeProvider("claude", ["ok"], interval=0.2),
    ])
    assert chain.min_interval() == 4.5
    chain.call("sys", "hola", {}, 512)
    assert chain.min_interval() == 0.2


# --- puente con el agente ---------------------------------------------------

def test_parse_decisions_accepts_abbreviations_and_comments():
    agent_filter = _load_agent_filter()
    decisions, errors = agent_filter.parse_decisions(
        "# cabecera\n"
        "1 pol 0.9\n"
        "2  non\n"
        "3 gar 0.7 tr\n"
        "4 political_article 0.5 boilerplate_residual\n"
        "\n"
    )
    assert errors == []
    assert decisions[1] == {"category": "political_article",
                            "confidence": 0.9, "text_issues": []}
    assert decisions[2]["category"] == "nonpolitical_article"
    assert decisions[2]["confidence"] == 0.9, "confianza por defecto"
    assert decisions[3]["text_issues"] == ["truncado"]
    assert decisions[4]["text_issues"] == ["boilerplate_residual"]


def test_parse_decisions_reports_bad_lines_without_losing_good_ones():
    # Un typo en el artículo 300 no debe tirar las 299 decisiones anteriores.
    agent_filter = _load_agent_filter()
    decisions, errors = agent_filter.parse_decisions(
        "1 pol 0.9\n"
        "2 inventada 0.9\n"
        "x pol\n"
        "4\n"
        "5 pol 0.8 marcarara\n"
    )
    assert set(decisions) == {1, 5}
    assert len(errors) == 4


def test_parse_decisions_flags_duplicate_articles():
    agent_filter = _load_agent_filter()
    decisions, errors = agent_filter.parse_decisions("1 pol\n1 non\n")
    assert decisions[1]["category"] == "political_article"
    assert any("ya tenía decisión" in e for e in errors)


def test_stratified_sample_spreads_across_sources():
    # El JSONL sale ordenado por rondas: un corte por cabecera sobre-representa
    # a las fuentes rápidas y el prefilter aprendería "fuente", no politicidad.
    agent_filter = _load_agent_filter()
    articles = (
        [{"id": f"a{i}", "source": "dominante"} for i in range(500)]
        + [{"id": f"b{i}", "source": "rara"} for i in range(5)]
    )
    sample = agent_filter.stratified_sample(articles, limit=10, seed=1)

    sources = {a["source"] for a in sample}
    assert sources == {"dominante", "rara"}
    n_rara = sum(1 for a in sample if a["source"] == "rara")
    assert n_rara == 5, "la fuente pequeña debe entrar entera antes de repetir"


def test_stratified_sample_is_deterministic_per_seed():
    agent_filter = _load_agent_filter()
    articles = [{"id": f"a{i}", "source": f"s{i % 7}"} for i in range(200)]
    first = agent_filter.stratified_sample(articles, 20, seed=42)
    second = agent_filter.stratified_sample(articles, 20, seed=42)
    assert [a["id"] for a in first] == [a["id"] for a in second]


@pytest.mark.parametrize("issue", ["digest_multinoticia", "truncado",
                                   "preview_paywall"])
def test_blocking_issues_are_recognised(issue):
    from src.scraper.article_filter import BLOCKING_TEXT_ISSUES
    assert issue in BLOCKING_TEXT_ISSUES


# --- travesía con cursor reanudable -----------------------------------------

def _isolated_agent_filter(tmp_path, monkeypatch, articles):
    """agent_filter apuntando a un corpus y un estado temporales."""
    agent_filter = _load_agent_filter()
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        "\n".join(json.dumps(a, ensure_ascii=False) for a in articles) + "\n",
        encoding="utf-8")
    monkeypatch.setattr(agent_filter, "BATCH_DIR", tmp_path / "batches")
    monkeypatch.setattr(agent_filter, "STATE_PATH",
                        tmp_path / "batches" / "filter_state.json")
    monkeypatch.setattr(agent_filter, "LOGS_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir(exist_ok=True)
    return agent_filter, corpus


def _articles(n, start=0):
    return [{"id": f"id{i}", "title": f"Titular {i}", "text": f"Cuerpo {i} " * 30,
             "source": f"fuente{i % 3}", "url": f"http://x/{i}"}
            for i in range(start, start + n)]


def test_load_corpus_records_line_numbers(tmp_path, monkeypatch):
    # El cursor es un nº de línea: sin `_line` no se puede avanzar.
    agent_filter, corpus = _isolated_agent_filter(tmp_path, monkeypatch,
                                                  _articles(5))
    loaded = agent_filter.load_corpus(corpus)
    assert [a["_line"] for a in loaded] == [0, 1, 2, 3, 4]


def test_state_resets_when_the_input_corpus_changes(tmp_path, monkeypatch):
    # Un cursor de otro corpus saltaría artículos en silencio.
    agent_filter, corpus = _isolated_agent_filter(tmp_path, monkeypatch,
                                                  _articles(3))
    agent_filter.write_state({"input": str(corpus), "cursor": 99,
                              "batch_seq": 7, "session_tokens": 0,
                              "budget_tokens": 1000, "pending_batch": None})
    assert agent_filter.read_state(corpus)["cursor"] == 99
    assert agent_filter.read_state(tmp_path / "otro.jsonl")["cursor"] == 0


def test_budget_stops_before_handing_over_the_batch(tmp_path, monkeypatch,
                                                    capsys):
    # Entregar el lote y avisar después ya habría gastado el contexto que el
    # presupuesto existe para proteger.
    agent_filter, corpus = _isolated_agent_filter(tmp_path, monkeypatch,
                                                  _articles(40))
    args = argparse_namespace(input=str(corpus), size=10, budget=200,
                              reset_session=True, force=False)
    agent_filter.cmd_next(args)
    batches_before = len(list((tmp_path / "batches").glob("lote_*.txt")))

    # force salta la guarda de "lote sin ingerir" (que se dispara antes) para
    # que el test mida el corte por presupuesto y no esa otra protección.
    args.reset_session = False
    args.force = True
    capsys.readouterr()
    agent_filter.cmd_next(args)
    out = capsys.readouterr().out

    assert "PRESUPUESTO DE LA TANDA AGOTADO" in out
    assert len(list((tmp_path / "batches").glob("lote_*.txt"))) == batches_before


def test_pending_batch_blocks_the_next_one(tmp_path, monkeypatch, capsys):
    agent_filter, corpus = _isolated_agent_filter(tmp_path, monkeypatch,
                                                  _articles(40))
    args = argparse_namespace(input=str(corpus), size=5, budget=None,
                              reset_session=True, force=False)
    agent_filter.cmd_next(args)
    capsys.readouterr()

    args.reset_session = False
    with pytest.raises(SystemExit, match="sigue sin ingerir"):
        agent_filter.cmd_next(args)


def test_doubt_token_is_not_a_category():
    agent_filter = _load_agent_filter()
    decisions, errors = agent_filter.parse_decisions("1 dud\n2 ?\n3 duda\n4 pol\n")
    assert errors == []
    assert [decisions[i]["category"] for i in (1, 2, 3)] == \
        [agent_filter.DOUBT_TOKEN] * 3
    assert decisions[4]["category"] == "political_article"


def argparse_namespace(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)


# --- espera por límite de uso ------------------------------------------------

def _load_filter_runner():
    spec = importlib.util.spec_from_file_location(
        "filter_runner", ROOT / "scripts" / "filter_runner.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["filter_runner"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("message,hour,minute", [
    ("5-hour limit reached ∙ resets 8pm", 20, 0),
    ("Claude usage limit reached. Your limit will reset at 3:30 PM.", 15, 30),
    ("limit reached, resets at 09:15 am", 9, 15),
    ("resets 23:45", 23, 45),
])
def test_reads_the_announced_reset_time(message, hour, minute):
    # Dormir 4,5 h cuando faltaban 20 min tira media jornada de trabajo.
    from datetime import datetime, timedelta
    runner = _load_filter_runner()
    seconds = runner.seconds_until_reset(message)
    assert seconds is not None
    wake = datetime.now() + timedelta(seconds=seconds)
    assert (wake.hour, wake.minute) == (hour, minute + 2)


def test_falls_back_when_no_reset_time_is_announced():
    runner = _load_filter_runner()
    assert runner.seconds_until_reset("Claude usage limit reached.") is None
    assert runner.seconds_until_reset("resets at 99:99") is None
    assert runner.seconds_until_reset("nada que ver") is None


def test_detects_the_real_session_limit_message():
    """El mensaje real es "session limit", no "usage limit".

    Con una lista de frases literales esto no casaba con nada, el bucle lo
    trataba como fallo genérico y pasó media hora martilleando el límite en
    vez de dormir hasta la renovación anunciada.
    """
    runner = _load_filter_runner()
    real = "You've hit your session limit · resets 9:10pm (America/Bogota)"
    assert runner._USAGE_LIMIT_RE.search(real)
    assert runner.seconds_until_reset(real) is not None


@pytest.mark.parametrize("message", [
    "You've hit your session limit · resets 9:10pm (America/Bogota)",
    "Claude usage limit reached",
    "5-hour limit reached",
    "Weekly limit reached for Opus",
    "You are out of credits",
    "Your credit balance is too low",
])
def test_limit_messages_are_recognised(message):
    runner = _load_filter_runner()
    assert runner._USAGE_LIMIT_RE.search(message), message


@pytest.mark.parametrize("message", [
    "SyntaxError in agent_filter.py",
    "no such file or directory",
    "el lote 7 sigue sin ingerir",
])
def test_ordinary_failures_are_not_mistaken_for_limits(message):
    # Confundirlos haría dormir 4,5 h por un error de código.
    runner = _load_filter_runner()
    assert not runner._USAGE_LIMIT_RE.search(message), message


def test_usage_limit_and_transient_errors_are_told_apart():
    # Esperar 5 h por una sobrecarga pasajera, o reintentar cada 5 min contra
    # una ventana de 5 h, son los dos errores caros de este bucle.
    runner = _load_filter_runner()

    def kind(message):
        if runner._USAGE_LIMIT_RE.search(message):
            return "usage"
        if any(m in message.lower() for m in runner.TRANSIENT_MARKERS):
            return "transient"
        return "other"

    assert kind("Claude usage limit reached ∙ resets 8pm") == "usage"
    assert kind("You've hit your session limit · resets 9:10pm") == "usage"
    assert kind("Your credit balance is too low") == "usage"
    assert kind("API Error 529: overloaded_error") == "transient"
    assert kind("connection reset by peer") == "transient"
    assert kind("SyntaxError in agent_filter.py") == "other"


def test_default_usage_wait_is_a_full_limit_window():
    runner = _load_filter_runner()
    assert 4 * 3600 <= runner.DEFAULT_USAGE_WAIT <= 5 * 3600
    assert runner.TRANSIENT_WAIT <= 600


# --- puerta del límite semanal ----------------------------------------------

_USAGE_REAL = """You are currently using your subscription to power your Claude Code usage

Current session: 4% used · resets Sep 4 at 8pm (America/Bogota)
Current week (all models): 72% used · resets Sep 7 at 3:59pm (America/Bogota)
Current week (Fable): 1% used · resets Sep 7 at 4pm (America/Bogota)
"""


def test_reads_the_weekly_percent_from_real_usage_output():
    runner = _load_filter_runner()
    parsed = runner.parse_weekly_usage(_USAGE_REAL)
    assert parsed is not None
    pct, resets = parsed
    # Debe leer "all models", no la línea de un modelo suelto que va justo
    # debajo con otro porcentaje.
    assert pct == 72.0
    assert (resets.month, resets.day, resets.hour, resets.minute) == (9, 7, 15, 59)


def test_weekly_gate_ignores_the_session_line():
    # La línea de sesión aparece ANTES y también dice "% used": engancharse a
    # ella dejaría la puerta semanal sin efecto.
    runner = _load_filter_runner()
    pct, _ = runner.parse_weekly_usage(_USAGE_REAL)
    assert pct != 4.0


@pytest.mark.parametrize("line,expected", [
    ("Current week (all models): 0% used · resets Sep 7 at 4pm", 0.0),
    ("Current week (all models): 100% used · resets Dec 31 at 11:59pm", 100.0),
    ("current week (all models): 79.5% used", 79.5),
])
def test_weekly_percent_variants(line, expected):
    runner = _load_filter_runner()
    parsed = runner.parse_weekly_usage(line)
    assert parsed is not None and parsed[0] == expected


def test_unreadable_usage_returns_none_so_work_continues():
    # Fallar al leer el porcentaje no debe parar días de trabajo: el llamador
    # sigue trabajando y lo registra.
    runner = _load_filter_runner()
    assert runner.parse_weekly_usage("") is None
    assert runner.parse_weekly_usage("Current session: 4% used") is None
    assert runner.parse_weekly_usage("error: not logged in") is None


def test_weekly_percent_without_reset_date_still_parses():
    runner = _load_filter_runner()
    parsed = runner.parse_weekly_usage("Current week (all models): 85% used")
    assert parsed is not None
    assert parsed[0] == 85.0 and parsed[1] is None


def test_reset_date_rolls_over_the_year():
    from datetime import datetime
    runner = _load_filter_runner()
    target = runner._parse_reset_date("Jan 2 at 9am")
    assert target is not None
    assert target >= datetime.now() - __import__("datetime").timedelta(days=180)


def test_default_weekly_stop_leaves_headroom():
    runner = _load_filter_runner()
    assert 0 < runner.WEEKLY_STOP_PCT < 100


# --- el equipo no debe dormirse en la espera de sesión -----------------------

def test_only_the_weekly_wait_lets_the_machine_sleep(monkeypatch):
    """Regresión: soltar caffeinate en la espera de SESIÓN paró el trabajo.

    La espera por límite de sesión dura 1-5 h. Al soltar caffeinate en toda
    espera de más de una hora, el Mac se dormía y nadie lo despertaba a la
    hora anunciada: el servicio quedaba parado horas. Solo la espera SEMANAL
    (que puede durar días) justifica dejar dormir el equipo.
    """
    runner = _load_filter_runner()
    estados: list[bool] = []
    monkeypatch.setattr(runner, "caffeinate", lambda on: estados.append(on))
    monkeypatch.setattr(runner, "log", lambda *_: None)
    monkeypatch.setattr(runner.time, "sleep", lambda _: None)

    estados.clear()
    runner.sleep_interruptible(0, "límite de sesión")
    assert False not in estados, "la espera de sesión NO debe soltar caffeinate"

    estados.clear()
    runner.sleep_interruptible(0, "semanal", may_sleep_machine=True)
    assert False in estados, "la espera semanal sí debe soltarlo"


def test_wait_uses_an_absolute_deadline(monkeypatch):
    # Con una cuenta atrás de 60 en 60, una suspensión del equipo pierde el
    # tiempo real transcurrido y el servicio despierta tarde.
    runner = _load_filter_runner()
    monkeypatch.setattr(runner, "caffeinate", lambda on: None)
    monkeypatch.setattr(runner, "log", lambda *_: None)
    vueltas = {"n": 0}

    def fake_sleep(_):
        vueltas["n"] += 1
        if vueltas["n"] > 5:
            raise AssertionError("no converge: sigue siendo cuenta atrás")

    monkeypatch.setattr(runner.time, "sleep", fake_sleep)
    # 0 segundos: con plazo absoluto no entra al bucle ni una vez.
    runner.sleep_interruptible(0, "nada")
    assert vueltas["n"] == 0


# --- reponer materia prima cuando el filtrado no alcanza el mínimo -----------

def test_raw_needed_accounts_for_the_filter_keep_rate():
    """Pedir la diferencia en bruto se quedaría corto.

    El filtro conserva ~54%: para sumar ~16.500 filtrados hay que scrapear
    ~30.700 crudos, no 16.500.
    """
    runner = _load_filter_runner()
    # Todo decidido: es el caso real en el que se llama.
    faltan = runner.raw_needed(kept=27_123, decided=50_351, total=50_351,
                               objetivo=40_000)
    assert 23_000 <= faltan <= 25_500, faltan


def test_raw_needed_discounts_what_is_scraped_but_undecided():
    # Ignorar los pendientes mandaría al colector a por miles de artículos
    # que ya estaban en disco esperando decisión.
    runner = _load_filter_runner()
    con_pendientes = runner.raw_needed(kept=23_443, decided=43_518,
                                       total=50_351, objetivo=40_000)
    sin_pendientes = runner.raw_needed(kept=23_443, decided=43_518,
                                       total=43_518, objetivo=40_000)
    assert con_pendientes < sin_pendientes
    assert sin_pendientes - con_pendientes == pytest.approx(50_351 - 43_518, abs=2)


def test_raw_needed_never_divides_by_a_near_zero_rate():
    # Con tasa ~0 la división daría una cifra absurda y el colector
    # perseguiría un objetivo imposible durante días.
    runner = _load_filter_runner()
    faltan = runner.raw_needed(kept=0, decided=1000, total=1000, objetivo=40_000)
    assert faltan <= 40_000 / 0.05


def test_raw_needed_survives_an_empty_run():
    runner = _load_filter_runner()
    assert runner.raw_needed(0, 0, 0, 40_000) > 0


def test_collector_stops_being_retried_when_the_corpus_stops_growing(monkeypatch):
    # Si las fuentes están agotadas, reintentar para siempre dejaría el
    # servicio dormido sin avanzar nunca.
    runner = _load_filter_runner()
    monkeypatch.setattr(runner, "log", lambda *_: None)
    monkeypatch.setattr(runner, "collector_running", lambda: True)
    runner._last_total = None
    runner._stale_collect = 0

    state = {"total": 50_351, "decided": 50_351}
    assert runner.start_collector(state, kept=27_000) is True   # primera vez
    for _ in range(runner.MAX_STALE_COLLECTS - 1):
        assert runner.start_collector(state, kept=27_000) is True
    assert runner.start_collector(state, kept=27_000) is False, \
        "tras varias comprobaciones sin crecer debe rendirse"


def test_growing_corpus_resets_the_stale_counter(monkeypatch):
    runner = _load_filter_runner()
    monkeypatch.setattr(runner, "log", lambda *_: None)
    monkeypatch.setattr(runner, "collector_running", lambda: True)
    runner._last_total = None
    runner._stale_collect = 0

    runner.start_collector({"total": 50_000, "decided": 50_000}, 27_000)
    runner.start_collector({"total": 50_000, "decided": 50_000}, 27_000)
    assert runner._stale_collect == 1
    runner.start_collector({"total": 51_200, "decided": 50_000}, 27_000)
    assert runner._stale_collect == 0, "si el corpus creció, se reinicia"


def test_min_corpus_default_matches_the_thesis_target():
    runner = _load_filter_runner()
    assert runner.MIN_CORPUS == 40_000


def test_collect_extra_overrides_the_computed_deficit(monkeypatch):
    """Una cantidad fija de crudos manda sobre el cálculo por déficit.

    Cuánto debe crecer el corpus es una decisión del usuario, no algo que
    deba deducirse de la tasa de conservación.
    """
    runner = _load_filter_runner()
    pedidos = {}
    monkeypatch.setattr(runner, "log", lambda *_: None)
    monkeypatch.setattr(runner, "collector_running", lambda: False)
    monkeypatch.setattr(runner, "COLLECT_EXTRA", 50_000)

    def fake_run(cmd, **kwargs):
        if "--target" in cmd:
            pedidos["target"] = int(cmd[cmd.index("--target") + 1])
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._last_total = None
    runner._stale_collect = 0
    runner.start_collector({"total": 50_351, "decided": 50_351}, kept=27_123)

    assert pedidos["target"] == 100_351, pedidos


def test_build_corpus_returns_the_article_count():
    """El traspaso filtrado→scraping depende de este número.

    Regresión: `build_corpus` no aceptaba `verbose` ni devolvía nada, así que
    al completarse el filtrado el runner reventaba con TypeError justo en el
    punto donde debía arrancar el colector, y launchd lo relanzó en bucle
    durante horas sin que nadie recogiera un artículo más.
    """
    import inspect
    runner = _load_filter_runner()
    firma = inspect.signature(runner.build_corpus)
    assert "verbose" in firma.parameters
    assert firma.return_annotation is int


def test_completion_path_starts_the_collector_when_short(monkeypatch):
    runner = _load_filter_runner()
    llamado = {}
    monkeypatch.setattr(runner, "log", lambda *_: None)
    monkeypatch.setattr(runner, "caffeinate", lambda on: None)
    monkeypatch.setattr(runner, "build_corpus", lambda verbose=True: 27_084)
    monkeypatch.setattr(runner, "collector_running", lambda: False)
    monkeypatch.setattr(runner, "COLLECT_EXTRA", 50_000)

    def fake_run(cmd, **kwargs):
        if "--target" in cmd:
            llamado["target"] = int(cmd[cmd.index("--target") + 1])
        class R:
            returncode = 0
            stdout = stderr = ""
        return R()

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner._last_total = None
    runner._stale_collect = 0

    ok = runner.start_collector({"total": 50_351, "decided": 50_351},
                                kept=27_084)
    assert ok and llamado["target"] == 100_351


def test_filter_does_not_finish_while_the_collector_is_still_scraping():
    """El filtro (~1.800/h) adelanta al colector (~700/h).

    Sin esta guarda alcanzaba el mínimo, se declaraba terminado y se apagaba
    mientras el colector seguía dos días recogiendo artículos que ya nadie
    iba a decidir.
    """
    runner = _load_filter_runner()
    minimo = runner.MIN_CORPUS

    assert runner.should_finish(minimo, collector_active=False)
    assert not runner.should_finish(minimo, collector_active=True), \
        "no debe cerrar mientras se sigue scrapeando"
    assert not runner.should_finish(minimo - 1, collector_active=False), \
        "no debe cerrar por debajo del mínimo"
    assert not runner.should_finish(minimo - 1, collector_active=True)


def test_session_and_weekly_limits_have_independent_switches(monkeypatch):
    """Un solo interruptor obligaba a elegir mal.

    La sesión se renueva en horas (esperar es correcto); la semanal en días
    (esperar deja el proceso vivo días y suelta caffeinate). Con una sola
    variable, "no pares en la sesión" implicaba "duerme una semana", y
    "para en la semanal" implicaba "para al primer corte de sesión".
    """
    runner = _load_filter_runner()
    # Por defecto: la sesión espera, la semanal para.
    assert runner.STOP_ON_SESSION_LIMIT is False
    assert runner.WEEKLY_WAIT is False

    monkeypatch.setenv("FILTER_STOP_ON_SESSION_LIMIT", "1")
    assert _load_filter_runner().STOP_ON_SESSION_LIMIT is True
    monkeypatch.delenv("FILTER_STOP_ON_SESSION_LIMIT")

    monkeypatch.setenv("FILTER_WEEKLY_WAIT", "1")
    assert _load_filter_runner().WEEKLY_WAIT is True


def test_old_stop_on_limit_env_still_understood(monkeypatch):
    # Un plist ya instalado con el nombre viejo no debe cambiar de conducta
    # en silencio al actualizar el runner.
    monkeypatch.setenv("FILTER_STOP_ON_LIMIT", "1")
    assert _load_filter_runner().STOP_ON_SESSION_LIMIT is True


def test_stop_on_limit_is_opt_in_and_off_by_default(monkeypatch):
    """Agotar la cuota puede significar «espera» o «termina», según se pida.

    El servicio desatendido debe esperar la renovación; una corrida acotada
    ("trabaja lo que quede de sesión y para") debe terminar. Que el valor por
    defecto sea esperar importa: si un despliegue desatendido terminara al
    primer límite, se quedaría parado sin que nadie lo note.
    """
    runner = _load_filter_runner()
    assert runner.STOP_ON_SESSION_LIMIT is False

    for valor, esperado in (("", False), ("0", False), ("1", True),
                            ("si", True)):
        monkeypatch.setenv("FILTER_STOP_ON_SESSION_LIMIT", valor)
        recargado = _load_filter_runner()
        assert recargado.STOP_ON_SESSION_LIMIT is esperado, valor
