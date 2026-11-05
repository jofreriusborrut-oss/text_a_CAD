"""The whole chain on a real part: assistant -> CadQuery -> checks -> simulation -> printing.

Claude is replaced by recorded answers; everything else is real. These tests
need CadQuery, so they are skipped where it is not installed.
"""
from dataclasses import replace
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from textacad import assistant, checks, printability      # noqa: E402
from textacad.config import get_settings                  # noqa: E402
from textacad.materials import UseCase, recommend          # noqa: E402
from textacad.mesh import load_stl                         # noqa: E402
from textacad.prompts import EXAMPLE_NOTES, EXAMPLES, format_note   # noqa: E402
from textacad.sandbox import run_code                      # noqa: E402
from textacad.session import DesignSession                 # noqa: E402
from textacad.simulate import LoadCase, run_simulation     # noqa: E402

from .fake_claude import make_fake_claude, read_call       # noqa: E402

REQUEST, CLAMP = EXAMPLES[-1]
NOTE = EXAMPLE_NOTES[-1]
CLAMP_V2 = (Path(__file__).parent / "parts" / "f_abracadora.py").read_text(encoding="utf-8")
NOTE_V2 = {"title": NOTE["title"],
           "summary": "Ara l'anell fa 26 mm d'alçada, té dos cargols M5 de tancament i un xamfrà d'entrada d'1 mm.",
           "changes": ["Alçada: de 20 a 26 mm.", "Cargols de tancament: d'1 a 2.", "Xamfrà d'entrada nou: 1 mm."],
           "use": NOTE["use"]}


def answer(note, code):
    return format_note(note) + f"```python\n{code}```\n"


def holes(info):
    return {(round(h["diameter"], 2), h["axis"]): h["count"] for h in info["holes"]}


def test_design_then_change_on_the_real_runner(tmp_path):
    fake = make_fake_claude(tmp_path, [answer(NOTE, CLAMP), answer(NOTE_V2, CLAMP_V2)])
    settings = replace(get_settings(), backend="cli", cli_path=fake, exec_timeout=60, max_attempts=3,
                       sessions_dir=tmp_path / "sessions")
    session = DesignSession(tmp_path / "sessions")

    first = assistant.handle_message(session, REQUEST, settings=settings)
    assert first.ok and first.version.number == 1, first.last_error
    assert [a.error for a in first.attempts] == [None]             # right at the first attempt
    v1 = first.version
    assert v1.info["notes"] == []
    assert holes(v1.info) == {(3.3, "x"): 1, (5.5, "y"): 1, (52.3, "z"): 1}
    assert v1.note["use"] == {"process": "fdm", "max_temp_c": 90.0, "outdoor": True, "fluids": True, "vibration": True}
    assert {"metric-m4", "metric-m5"} <= set(v1.components)
    for name in ("part.step", "part.stl", "part.3mf", "reference.stl", "code.py"):
        assert session.file_path(1, name).exists(), name
    levels = {c.code: c.level for c in checks.run_checks(v1.info, session.file_path(1, "part.stl").read_bytes())}
    assert levels == {"solid_ok": "ok", "size_ok": "ok", "holes_ok": "ok", "fit_ok": "ok", "walls_ok": "ok",
                      "mass": "info"}

    second = assistant.handle_message(
        session, "Fes-la de 26 mm d'alçada, amb dos cargols de tancament i un xamfrà d'entrada al forat.",
        settings=settings)
    assert second.ok and second.version.number == 2 and second.version.parent == 1, second.last_error
    v2 = second.version
    assert v2.info["bbox"]["size"] == pytest.approx([85.15, 62.3, 26.0], abs=0.01)
    assert holes(v2.info) == {(3.3, "x"): 1, (5.5, "y"): 2, (52.3, "z"): 1}
    assert v2.info["volume_mm3"] > v1.info["volume_mm3"]
    assert v2.note["changes"][0] == "Alçada: de 20 a 26 mm."
    # The change request carried the current script and what was measured on it.
    sent = read_call(tmp_path, 2)["stdin"]
    assert "Current script (the part as it is now):" in sent and '"tube_diameter"' in sent
    assert "overall size X x Y x Z = 85.15 x 62.30 x 20.00 mm" in sent
    assert "1 x d3.3 (axis x), 1 x d5.5 (axis y), 1 x d52.3 (axis z)" in sent
    assert "Fes-la de 26 mm" in sent

    again = DesignSession.load(session.id, tmp_path / "sessions")
    assert [v.number for v in again.versions] == [1, 2] and again.current == 2
    assert again.history() == [REQUEST, "Fes-la de 26 mm d'alçada, amb dos cargols de tancament i un xamfrà d'entrada al forat."]


def test_simulation_and_printing_on_the_real_clamp():
    run = run_code(CLAMP)
    try:
        assert run.ok, run.error
        mesh = load_stl(run.stl_path.read_bytes())
        info = run.info
    finally:
        run.cleanup()
    assert mesh.is_watertight()
    assert mesh.volume == pytest.approx(info["volume_mm3"], rel=0.01)

    case = LoadCase.from_dict(info["load_case"])
    result = run_simulation(mesh, case, "petg", "draft")
    summary = result.summary()
    assert result.equilibrium_error < 1e-3
    assert summary["applied_force_n"] == pytest.approx([0, 0, 30], abs=1e-6)
    assert summary["reaction_force_n"] == pytest.approx([0, 0, -30], abs=0.05)
    assert abs(result.volume_error) < 0.15
    # 30 N on a clamp with 5 mm walls: well below 1 MPa and a few hundredths of a millimetre at most.
    assert 0.01 < result.max_stress < 5
    assert 0 < result.max_displacement < 0.2
    assert result.safety_factor > 5
    drawing = result.drawing_data()
    assert drawing["points"] and drawing["triangles"] and drawing["scale_max_mpa"] > 0

    data = printability.analyse(mesh, "asa")
    assert data["best"]["up"] in ("+z", "-z")                       # ring flat on the bed
    assert data["best"]["height_mm"] == pytest.approx(20)
    assert any(p["fits"] for p in data["printers"])
    assert 5 < data["estimate"]["mass_g"] < 60

    use = UseCase.from_dict({"process": "fdm", "max_temp_c": 90, "outdoor": True, "fluids": True, "vibration": True,
                             "stress_mpa": result.max_stress})
    best = recommend(use)[0]
    assert best.suitable and best.material.id not in ("pla", "petg") and best.safety_factor > best.required_factor
