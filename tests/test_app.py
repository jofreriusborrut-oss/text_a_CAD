"""The Streamlit app end to end, with a fake `claude` (no real Claude calls)."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from textacad.prompts import EXAMPLE_FLANGE

from .fake_claude import make_fake_claude

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app(tmp_path, monkeypatch):
    _, code = EXAMPLE_FLANGE
    monkeypatch.setenv("CLAUDE_CLI_PATH", make_fake_claude(tmp_path, [f"```python\n{code}```"]))
    monkeypatch.setenv("CLAUDE_BACKEND", "cli")
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    at.text_area[0].input("Brida circular de 80 mm amb 6 forats M6")
    at.button[0].click().run()      # "Genera la peça" (form submit)
    assert not at.exception
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
