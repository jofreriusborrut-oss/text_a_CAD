"""Hand-written CadQuery code runs in the sandbox, is exported and MEASURED.

These tests need CadQuery (they are skipped where it is not installed) and
do NOT call Claude.
"""
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from textacad import checks                      # noqa: E402
from textacad.mesh import load_stl               # noqa: E402
from textacad.params import extract_params       # noqa: E402
from textacad.prompts import EXAMPLE_NOTES, EXAMPLES   # noqa: E402
from textacad.sandbox import run_code            # noqa: E402

PARTS = sorted((Path(__file__).parent / "parts").glob("*.py"))
EXAMPLE_IDS = [note["title"] for note in EXAMPLE_NOTES]


def _check_ok(res):
    assert res.ok, res.error
    assert res.info["is_valid"]
    assert res.info["n_solids"] == 1
    assert res.step_path.stat().st_size > 1000
    assert res.stl_path.stat().st_size > 1000
    size = res.info["bbox"]["size"]
    expected = res.info["expected_bbox"]
    assert expected is not None, "EXPECTED_BBOX missing"
    for got, want in zip(size, expected):
        assert got == pytest.approx(want, abs=0.2)
    assert res.info["notes"] == [], res.info["notes"]        # every extra measurement worked


def holes_of(res):
    return {(round(h["diameter"], 2), h["axis"]): h["count"] for h in res.info["holes"]}


@pytest.mark.parametrize("path", PARTS, ids=lambda p: p.stem)
def test_reference_parts(path):
    code = path.read_text(encoding="utf-8")
    extract_params(code)                     # PARAMS is well formed
    res = run_code(code)
    try:
        _check_ok(res)
    finally:
        res.cleanup()


@pytest.mark.parametrize("example", EXAMPLES, ids=EXAMPLE_IDS)
def test_prompt_examples_are_valid(example):
    """The examples Claude learns from must build AND pass every check of the app."""
    _, code = example
    extract_params(code)
    res = run_code(code)
    try:
        _check_ok(res)
        assert res.info["expected_holes"] is not None
        assert checks.problems_for_claude(res.info) is None
        levels = {c.code: c.level for c in checks.run_checks(res.info, res.stl_path.read_bytes())}
        assert "warning" not in levels.values() and "error" not in levels.values(), levels
    finally:
        res.cleanup()


def test_holes_are_found_on_the_real_geometry():
    expected = {
        "a_placa": {(6.5, "z"): 4},
        "b_escaire": {(5.0, "z"): 2, (5.0, "x"): 2},
        "c_casquet": {(8.0, "z"): 1},
        "d_caixa": {},
        "e_suport_bici": {(6.6, "z"): 3},
        # Two pinch bolts, each crossing both ears: two holes, not four.
        "f_abracadora": {(3.3, "x"): 1, (5.5, "y"): 2, (52.3, "z"): 1},
    }
    for path in PARTS:
        res = run_code(path.read_text(encoding="utf-8"))
        try:
            assert res.ok, res.error
            assert holes_of(res) == expected[path.stem], path.stem
        finally:
            res.cleanup()


def test_holes_of_the_prompt_examples():
    found = {}
    for note, (_, code) in zip(EXAMPLE_NOTES, EXAMPLES):
        res = run_code(code)
        try:
            assert res.ok, res.error
            found[note["title"]] = holes_of(res)
        finally:
            res.cleanup()
    assert found["brida-80"] == {(6.6, "z"): 6, (30.0, "z"): 1}
    assert found["suport-u"] == {}                                   # a slot is not a round hole
    assert found["eix-esglaonat"] == {(4.0, "x"): 1}
    assert found["caixa-electronica"] == {(2.5, "z"): 4}
    # Fork clamp: slit bore (52.3), pinch bolt across both ears (one hole) and the stud hole.
    assert found["abracadora-sensor-forquilla"] == {(3.3, "x"): 1, (5.5, "y"): 1, (52.3, "z"): 1}


def test_hole_details_and_centre_of_mass():
    code = (Path(__file__).parent / "parts" / "a_placa.py").read_text(encoding="utf-8")
    res = run_code(code)
    try:
        info = res.info
        assert len(info["hole_list"]) == 4
        centres = sorted((round(h["center"][0], 2), round(h["center"][1], 2)) for h in info["hole_list"])
        assert centres == [(-20.0, -30.0), (-20.0, 30.0), (20.0, -30.0), (20.0, 30.0)]
        assert all(h["length"] == pytest.approx(5.0, abs=1e-6) for h in info["hole_list"])
        assert info["center_of_mass"] == pytest.approx([0, 0, 2.5], abs=1e-6)
        assert info["n_faces"] > 6
    finally:
        res.cleanup()


def test_reference_component_and_load_case():
    code = EXAMPLES[EXAMPLE_IDS.index("abracadora-sensor-forquilla")][1]
    res = run_code(code)
    try:
        info = res.info
        assert info["reference"]["volume_mm3"] == pytest.approx(3.14159265 * 26 ** 2 * 50, rel=1e-3)
        assert info["reference"]["interference_mm3"] == pytest.approx(0, abs=0.5)
        assert res.reference_path.exists() and load_stl(res.reference_path.read_bytes()).is_watertight()
        case = info["load_case"]
        held = case["fixed"][0]
        assert (held["type"], held["axis"], held["center"]) == ("hole", "z", [0.0, 0.0, 0.0])
        assert held["diameter"] == pytest.approx(52.3)
        assert case["loads"][0]["force"] == [0.0, 0.0, 30.0]
        assert case["loads"][0]["region"]["center"] == pytest.approx([40.0, 0.0, 10.0])
        assert checks.check_fit(info).code == "fit_ok"
    finally:
        res.cleanup()


def test_collision_with_the_reference_is_measured():
    code = EXAMPLES[EXAMPLE_IDS.index("abracadora-sensor-forquilla")][1]
    # A tube 2 mm bigger than the bore: the clamp no longer fits.
    code = code.replace("REFERENCE = cq.Workplane(\"XY\").workplane(offset=-15).circle(D / 2)",
                        "REFERENCE = cq.Workplane(\"XY\").workplane(offset=-15).circle(D / 2 + 1)")
    res = run_code(code)
    try:
        assert res.info["reference"]["interference_mm3"] > 500
        assert checks.check_fit(res.info).code == "fit_collision"
        assert "overlaps the REFERENCE" in checks.problems_for_claude(res.info)
    finally:
        res.cleanup()


def test_exports_for_printing():
    code = (Path(__file__).parent / "parts" / "c_casquet.py").read_text(encoding="utf-8")
    res = run_code(code)
    try:
        mesh = load_stl(res.stl_path.read_bytes())
        assert mesh.is_watertight()
        assert mesh.volume == pytest.approx(res.info["volume_mm3"], rel=0.01)
        assert res.info["has_3mf"] and res.threemf_path.stat().st_size > 500
        assert set(res.files()) == {"part.step", "part.stl", "part.3mf"}
        assert b"ISO-10303-21" in res.step_path.read_bytes()[:200]
    finally:
        res.cleanup()


def test_syntax_error_is_reported():
    res = run_code("PARAMS = {}\nresult = (\n")
    assert not res.ok and "SyntaxError" in res.error


def test_cadquery_error_is_reported():
    code = "import cadquery as cq\nresult = cq.Workplane('XY').box(10, 10, 2).edges().fillet(5)\n"
    res = run_code(code)
    assert not res.ok
    assert "generated_part.py" in res.error


def test_missing_result():
    res = run_code("import cadquery as cq\nx = cq.Workplane('XY').box(1, 1, 1)\n")
    assert not res.ok and "result" in res.error


def test_forbidden_code_is_not_run(tmp_path):
    target = tmp_path / "written.txt"
    code = f"import cadquery as cq\nopen({str(target)!r}, 'w').write('x')\nresult = cq.Workplane('XY').box(1, 1, 1)\n"
    res = run_code(code)
    assert not res.ok and "not allowed" in res.error and not target.exists()


def test_timeout_kills_the_process():
    res = run_code("while True:\n    pass\n", timeout=3)
    assert not res.ok and "TimeoutError" in res.error
