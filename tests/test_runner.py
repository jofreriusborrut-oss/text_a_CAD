"""Phase 1: hand-written CadQuery code runs in the sandbox and exports STEP/STL.

These tests do NOT call Claude.
"""
from pathlib import Path

import pytest

from textacad.params import extract_params
from textacad.prompts import EXAMPLES
from textacad.sandbox import run_code

PARTS = sorted((Path(__file__).parent / "parts").glob("*.py"))


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


@pytest.mark.parametrize("path", PARTS, ids=lambda p: p.stem)
def test_reference_parts(path):
    code = path.read_text(encoding="utf-8")
    extract_params(code)                     # PARAMS is well formed
    _check_ok(run_code(code))


@pytest.mark.parametrize("example", EXAMPLES, ids=["flange", "u_bracket", "shaft", "enclosure"])
def test_prompt_examples_are_valid(example):
    _, code = example
    extract_params(code)
    _check_ok(run_code(code))


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


def test_timeout_kills_the_process():
    res = run_code("while True:\n    pass\n", timeout=3)
    assert not res.ok and "TimeoutError" in res.error
