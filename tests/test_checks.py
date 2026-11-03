"""Phase 5: automatic checks on the 5 reference parts and on bad parts."""
from pathlib import Path

import pytest

from textacad.checks import run_checks
from textacad.params import apply_values
from textacad.sandbox import run_code

PARTS = {p.stem: p.read_text(encoding="utf-8") for p in (Path(__file__).parent / "parts").glob("*.py")}


def checks_for(code):
    run = run_code(code)
    assert run.ok, run.error
    try:
        return {c.title: c for c in run_checks(run.info, run.stl_path.read_bytes())}, run.info
    finally:
        run.cleanup()


@pytest.mark.parametrize("name", sorted(PARTS))
def test_reference_parts_pass_all_checks(name):
    checks, _ = checks_for(PARTS[name])
    levels = [c.level for c in checks.values()]
    assert "error" not in levels and "warning" not in levels, checks


def test_thin_walls_are_detected():
    checks, _ = checks_for(apply_values(PARTS["d_caixa"], {"wall": 0.8}))
    thin = [c for c in checks.values() if c.title.startswith("Parets primes")]
    assert thin and thin[0].level == "warning"


def test_wrong_size_is_detected():
    code = PARTS["a_placa"].replace("EXPECTED_BBOX = (L, W, T)", "EXPECTED_BBOX = (L, W + 10, T)")
    checks, _ = checks_for(code)
    assert any(c.level == "warning" and "NO coincideix" in c.title for c in checks.values())


def test_rotated_size_is_only_info():
    code = PARTS["a_placa"].replace("EXPECTED_BBOX = (L, W, T)", "EXPECTED_BBOX = (W, L, T)")
    checks, _ = checks_for(code)
    assert any(c.level == "info" and "orientació" in c.title for c in checks.values())


def test_two_separate_solids_is_an_error():
    code = ("import cadquery as cq\n"
            "result = cq.Workplane('XY').box(10, 10, 10).union(\n"
            "    cq.Workplane('XY').center(30, 0).box(10, 10, 10))\n"
            "EXPECTED_BBOX = (40, 10, 10)\n")
    checks, info = checks_for(code)
    assert info["n_solids"] == 2
    assert any(c.level == "error" for c in checks.values())


def test_weight_in_pla():
    checks, info = checks_for(PARTS["d_caixa"])
    weight = [c for c in checks.values() if c.title.startswith("Volum")][0]
    grams = info["volume_mm3"] / 1000 * 1.24
    assert f"{grams:.1f}".replace(".", ",") in weight.title
