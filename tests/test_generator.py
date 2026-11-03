"""Claude backends and the correction loop, WITHOUT calling Claude.

A fake `claude` executable (tests/fake_claude.py) plays Claude's role.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from textacad.config import get_settings
from textacad.generator import ClaudeError, extract_code, generate_code, generate_part

from .fake_claude import make_fake_claude, read_call

GOOD = (Path(__file__).parent / "parts" / "c_casquet.py").read_text(encoding="utf-8")
# Same part with a classic CadQuery mistake: a fillet bigger than the wall.
BROKEN = GOOD.replace("result = result.edges().chamfer(C)", "result = result.edges().fillet(50)")
NO_PARAMS = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 10)\n"


def fenced(code: str) -> str:
    return f"Here is the script:\n```python\n{code}```\n"


def settings_for(fake: str):
    return replace(get_settings(), backend="cli", cli_path=fake, model="claude-sonnet-5-5", exec_timeout=30)


def test_extract_code_from_fenced_answer():
    answer = "Here you go:\n```python\nPARAMS = {}\nresult = 1\n```\nBye"
    assert extract_code(answer) == "PARAMS = {}\nresult = 1\n"


def test_extract_code_plain():
    assert extract_code("PARAMS = {}\n") == "PARAMS = {}\n"


def test_cli_backend_calls_claude_p(tmp_path):
    fake = make_fake_claude(tmp_path, ["```python\nPARAMS = {}\nresult = 42\n```"])
    code = generate_code("Placa de 10x10x2 mm", settings_for(fake))
    assert code == "PARAMS = {}\nresult = 42\n"
    call = read_call(tmp_path, 1)
    assert call["argv"][0] == "-p"
    assert "--model" in call["argv"] and "claude-sonnet-5-5" in call["argv"]
    assert "--system-prompt-file" in call["argv"]
    assert "Placa de 10x10x2 mm" in call["stdin"]


def test_works_at_first_attempt(tmp_path):
    fake = make_fake_claude(tmp_path, [fenced(GOOD)])
    progress = []
    gen = generate_part("Casquet", on_progress=lambda *a: progress.append(a), settings=settings_for(fake))
    assert gen.ok and len(gen.attempts) == 1
    assert gen.run.stl_path.exists()
    assert gen.params["outer_diameter"]["value"] == 20
    assert progress[0][:2] == (1, 3)


def test_error_is_sent_back_and_fixed(tmp_path):
    fake = make_fake_claude(tmp_path, [fenced(BROKEN), fenced(GOOD)])
    gen = generate_part("Casquet", settings=settings_for(fake))
    assert gen.ok
    assert [a.error is None for a in gen.attempts] == [False, True]
    second = read_call(tmp_path, 2)["stdin"]
    assert "fillet(50)" in second                      # previous code is sent back
    assert "generated_part.py" in second               # ...with the traceback
    assert "Casquet" in second                         # ...and the original description


def test_bad_params_counts_as_an_error(tmp_path):
    fake = make_fake_claude(tmp_path, [fenced(NO_PARAMS), fenced(GOOD)])
    gen = generate_part("Casquet", settings=settings_for(fake))
    assert gen.ok and len(gen.attempts) == 2
    assert "PARAMS" in gen.attempts[0].error


def test_gives_up_after_three_attempts(tmp_path):
    fake = make_fake_claude(tmp_path, [fenced(BROKEN)])
    progress = []
    gen = generate_part("Casquet", on_progress=lambda *a: progress.append(a), settings=settings_for(fake))
    assert not gen.ok
    assert len(gen.attempts) == 3
    assert {p[0] for p in progress} == {1, 2, 3}
    assert gen.last_error


def test_missing_cli_raises_clear_error():
    settings = replace(get_settings(), backend="cli", cli_path=None)
    import shutil

    if shutil.which("claude"):
        pytest.skip("claude is installed here")
    with pytest.raises(ClaudeError):
        generate_part("x", settings=settings)
