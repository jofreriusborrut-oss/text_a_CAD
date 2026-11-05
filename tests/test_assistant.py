"""The conversational assistant, with a fake `claude` and a fake CadQuery runner."""
from dataclasses import replace

import pytest

from textacad import assistant
from textacad.config import get_settings
from textacad.generator import ClaudeError, generate_part
from textacad.session import DesignSession

from . import fake_runner
from .fake_claude import make_fake_claude, read_call
from .fake_runner import PLATE, answer

THICK = PLATE.replace('"thickness": {"value": 5', '"thickness": {"value": 8')
WRONG_SIZE = PLATE.replace("EXPECTED_BBOX = (L, W, T)", "EXPECTED_BBOX = (L, W + 10, T)")
WRONG_HOLES = PLATE.replace("EXPECTED_HOLES = [(6.6, N)]", "EXPECTED_HOLES = [(6.6, N + 2)]")
BROKEN = PLATE.replace(".hole(6.6, N)", ".hole(6.6, N).fillet(50)")
UNSAFE = PLATE.replace("import cadquery as cq", "import cadquery as cq\nimport os")


@pytest.fixture(autouse=True)
def no_cadquery(monkeypatch):
    monkeypatch.setattr(assistant, "run_code", fake_runner.run_code)


def settings_for(tmp_path, answers, attempts=4):
    fake = make_fake_claude(tmp_path, answers)
    return replace(get_settings(), backend="cli", cli_path=fake, model="claude-sonnet-5-5",
                   exec_timeout=30, max_attempts=attempts, sessions_dir=tmp_path / "sessions")


def new_session(tmp_path):
    return DesignSession(tmp_path / "sessions")


def test_first_message_creates_version_one(tmp_path):
    settings = settings_for(tmp_path, [answer(PLATE)])
    session = new_session(tmp_path)
    events = []
    out = assistant.handle_message(session, "Placa de 60x40x5 amb 4 forats M6", events.append, settings)
    assert out.ok and out.version.number == 1 and out.version.parent is None
    assert out.version.note["summary"].startswith("Placa de 60")
    assert out.version.note["use"] == {"process": "fdm", "vibration": False}
    assert out.version.components == ["metric-m6"]
    assert out.version.info["load_case"]["fixed"][0] == {"type": "side", "side": "-x", "depth": 0.0}
    assert [e["stage"] for e in events] == ["asking", "running", "checking", "done"]
    assert [m["role"] for m in session.messages] == ["user", "assistant"]
    assert session.messages[1]["kind"] == "design" and session.messages[1]["version"] == 1
    sent = read_call(tmp_path, 1)["stdin"]
    assert "Part description:" in sent and "Placa de 60x40x5" in sent
    assert "M6 metric fastener" in sent and "clearance_hole_medium = 6.6" in sent      # catalogue data injected


def test_change_request_sends_the_current_script_and_measurements(tmp_path):
    settings = settings_for(tmp_path, [answer(PLATE), answer(THICK, changes=["Gruix: de 5 a 8 mm."])])
    session = new_session(tmp_path)
    assistant.handle_message(session, "Placa de 60x40x5 amb 4 forats M6", settings=settings)
    out = assistant.handle_message(session, "Fes-la de 8 mm de gruix", settings=settings)
    assert out.ok and out.version.number == 2 and out.version.parent == 1
    assert out.version.values["thickness"] == 8 and out.version.info["bbox"]["size"] == [60, 40, 8]
    assert out.version.note["changes"] == ["Gruix: de 5 a 8 mm."]
    sent = read_call(tmp_path, 2)["stdin"]
    assert "Current script (the part as it is now):" in sent
    assert '"thickness": {"value": 5' in sent                       # the script of version 1
    assert "overall size X x Y x Z = 60.00 x 40.00 x 5.00 mm" in sent
    assert "round holes found: 4 x d6.6 (axis z)" in sent
    assert "1. Placa de 60x40x5 amb 4 forats M6" in sent            # what was asked before
    assert "Change requested by the user:\nFes-la de 8 mm de gruix" in sent
    assert session.current == 2 and len(session.versions) == 2


def test_change_uses_the_slider_values_of_the_current_version(tmp_path):
    settings = settings_for(tmp_path, [answer(PLATE), answer(THICK)])
    session = new_session(tmp_path)
    assistant.handle_message(session, "Placa de 60x40x5", settings=settings)
    moved = PLATE.replace('"length": {"value": 60', '"length": {"value": 90')
    run = fake_runner.run_code(moved)
    session.update_version(1, moved, {"length": 90, "width": 40, "thickness": 5, "hole_count": 4}, run.info, run.files())
    assistant.handle_message(session, "Més gruixuda", settings=settings)
    sent = read_call(tmp_path, 2)["stdin"]
    assert '"length": {"value": 90' in sent and "90.00 x 40.00 x 5.00" in sent


def test_continue_from_an_older_version(tmp_path):
    settings = settings_for(tmp_path, [answer(PLATE), answer(THICK), answer(THICK)])
    session = new_session(tmp_path)
    assistant.handle_message(session, "Placa", settings=settings)
    assistant.handle_message(session, "Més gruixuda", settings=settings)
    out = assistant.handle_message(session, "Una altra idea a partir de la primera", settings=settings, base=1)
    assert out.version.number == 3 and out.version.parent == 1
    assert session.history(3) == ["Placa", "Una altra idea a partir de la primera"]


@pytest.mark.parametrize("bad, expected_text", [
    (WRONG_SIZE, "EXPECTED_BBOX says 60.00 x 50.00 x 5.00"),
    (WRONG_HOLES, "EXPECTED_HOLES says 6 round hole(s) of diameter 6.6"),
    (BROKEN, "fillet too big"),
    (UNSAFE, "`import os` is not allowed"),
])
def test_problems_are_sent_back_and_fixed(tmp_path, bad, expected_text):
    settings = settings_for(tmp_path, [answer(bad), answer(PLATE)])
    session = new_session(tmp_path)
    events = []
    out = assistant.handle_message(session, "Placa de 60x40x5 amb 4 forats M6", events.append, settings)
    assert out.ok and len(out.attempts) == 2
    assert [a.error is None for a in out.attempts] == [False, True]
    second = read_call(tmp_path, 2)["stdin"]
    assert expected_text in second
    assert "Placa de 60x40x5 amb 4 forats M6" in second            # the original request is repeated
    assert "attempt 1 of 4" in second
    assert "fixing" in [e["stage"] for e in events]
    assert out.version.attempts == [{"number": 1, "error": out.attempts[0].error}, {"number": 2, "error": None}]


def test_mismatch_is_kept_with_warning_on_the_last_attempt(tmp_path):
    settings = settings_for(tmp_path, [answer(WRONG_SIZE)], attempts=2)
    session = new_session(tmp_path)
    events = []
    out = assistant.handle_message(session, "Placa", events.append, settings)
    assert out.ok and len(out.attempts) == 2 and out.attempts[-1].error
    assert events[-1]["stage"] == "done_with_warnings"


def test_gives_up_when_the_script_never_runs(tmp_path):
    settings = settings_for(tmp_path, [answer(BROKEN)], attempts=3)
    session = new_session(tmp_path)
    out = assistant.handle_message(session, "Placa", settings=settings)
    assert not out.ok and out.kind == "failed" and len(out.attempts) == 3
    assert session.versions == [] and session.messages[-1]["kind"] == "failed"
    assert "fillet too big" in session.messages[-1]["error"]


def test_questions_instead_of_a_part(tmp_path):
    settings = settings_for(tmp_path, [answer(None, summary="Necessito saber què vols construir.",
                                              questions=["Quina peça és?", "Quines mides té?"])])
    session = new_session(tmp_path)
    out = assistant.handle_message(session, "Fes-me una peça", settings=settings)
    assert out.kind == "questions" and out.version is None
    assert session.messages[-1]["kind"] == "questions"
    assert session.messages[-1]["note"]["questions"] == ["Quina peça és?", "Quines mides té?"]


def test_bad_load_case_is_dropped_not_fatal(tmp_path):
    bad = PLATE.replace('"fixed": [{"type": "side", "side": "-x"}],', '"fixed": [{"type": "banana"}],')
    settings = settings_for(tmp_path, [answer(bad)])
    out = assistant.handle_message(new_session(tmp_path), "Placa", settings=settings)
    assert out.ok and out.version.info["load_case"] is None
    assert any("LOAD_CASE ignored" in n for n in out.version.info["notes"])


def test_claude_not_installed_is_a_clear_error(tmp_path):
    settings = replace(get_settings(), backend="cli", cli_path=str(tmp_path / "missing-claude"))
    with pytest.raises(ClaudeError, match="Could not start Claude Code"):
        assistant.handle_message(new_session(tmp_path), "Placa de 60x40x5", settings=settings)


def test_one_shot_generation_still_works(tmp_path):
    settings = settings_for(tmp_path, [answer(WRONG_SIZE), answer(PLATE)])
    progress = []
    gen = generate_part("Placa de 60x40x5", on_progress=lambda *a: progress.append(a), settings=settings)
    assert gen.ok and len(gen.attempts) == 2 and gen.note["title"] == "placa"
    assert progress[0][:2] == (1, 3) and {p[0] for p in progress} == {1, 2}
    gen.run.cleanup()
