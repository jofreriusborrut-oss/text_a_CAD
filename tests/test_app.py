"""The Streamlit app end to end, with a fake `claude` (no real Claude calls)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from textacad.prompts import EXAMPLE_FLANGE

from .fake_claude import make_fake_claude, read_call

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    _, code = EXAMPLE_FLANGE
    thicker = code.replace('"thickness": {"value": 8', '"thickness": {"value": 12')
    answers = [f"Aquí tens la brida.\n```python\n{code}```",
               f"Gruix de 8 a 12 mm.\n```python\n{thicker}```"]
    monkeypatch.setenv("CLAUDE_CLI_PATH", make_fake_claude(tmp_path, answers))
    monkeypatch.setenv("CLAUDE_BACKEND", "cli")
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.chat_input[0].set_value("Brida circular de 80 mm amb 6 forats M6").run()
    assert not at.exception
    at.tmp_path = tmp_path
    return at


def test_generate_shows_part_sliders_and_checks(app):
    labels = [s.label for s in app.slider]
    assert any("Nombre de forats" in l for l in labels)
    texts = " ".join(m.value for m in app.markdown)
    assert "80,0 × 80,0 × 8,0 mm" in texts
    assert any("Sòlid vàlid" in s.value for s in app.success)


def test_integer_slider_regenerates(app):
    count = next(s for s in app.slider if "Nombre de forats" in s.label)
    assert isinstance(count.value, int) and count.value == 6
    count.set_value(8).run()
    assert not app.exception
    code = next(c.value for c in app.code if "PARAMS" in c.value)
    assert '"bolt_count": {"value": 8' in code


def test_follow_up_message_modifies_the_same_part(app):
    app.chat_input[0].set_value("Fes-la de 12 mm de gruix").run()
    assert not app.exception
    texts = " ".join(m.value for m in app.markdown)
    assert "80,0 × 80,0 × 12,0 mm" in texts               # same flange, new thickness
    assert "Gruix de 8 a 12 mm." in texts                  # Claude's reply in the chat
    assert "versió 2" in texts
    sent = read_call(app.tmp_path, 2)["stdin"]
    assert '"thickness": {"value": 8' in sent              # the current part was sent
    assert "Brida circular de 80 mm amb 6 forats M6" in sent
