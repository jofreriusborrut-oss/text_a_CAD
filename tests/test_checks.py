"""Automatic checks on real CadQuery parts (skipped where CadQuery is not installed)."""
from pathlib import Path

import pytest

pytest.importorskip("cadquery")

from textacad.checks import run_checks            # noqa: E402
from textacad.params import apply_values          # noqa: E402
from textacad.sandbox import run_code             # noqa: E402

PARTS = {p.stem: p.read_text(encoding="utf-8") for p in (Path(__file__).parent / "parts").glob("*.py")}


def checks_for(code, material="petg"):
    run = run_code(code)
    assert run.ok, run.error
    try:
        return {c.code: c for c in run_checks(run.info, run.stl_path.read_bytes(), material)}, run.info
    finally:
        run.cleanup()


@pytest.mark.parametrize("name", sorted(PARTS))
def test_reference_parts_pass_all_checks(name):
    checks, _ = checks_for(PARTS[name])
    levels = [c.level for c in checks.values()]
    assert "error" not in levels and "warning" not in levels, checks
    assert "solid_ok" in checks and "size_ok" in checks and "walls_ok" in checks


def test_thin_walls_are_detected():
    checks, _ = checks_for(apply_values(PARTS["d_caixa"], {"wall": 0.8}))
    assert checks["walls_thin"].level == "warning"
    assert checks["walls_thin"].values["thinnest"] == pytest.approx(0.8, abs=0.05)


def test_wrong_size_is_detected():
    code = PARTS["a_placa"].replace("EXPECTED_BBOX = (L, W, T)", "EXPECTED_BBOX = (L, W + 10, T)")
    checks, _ = checks_for(code)
    assert checks["size_mismatch"].level == "warning"


def test_rotated_size_is_only_info():
    code = PARTS["a_placa"].replace("EXPECTED_BBOX = (L, W, T)", "EXPECTED_BBOX = (W, L, T)")
    checks, _ = checks_for(code)
    assert checks["size_rotated"].level == "info"


def test_wrong_number_of_holes_is_detected():
    code = PARTS["a_placa"] + "\nEXPECTED_HOLES = [(HD, 6)]\n"
    checks, _ = checks_for(code)
    assert checks["holes_mismatch"].level == "warning"
    assert checks["holes_mismatch"].values["hole_problems"] == [{"diameter": 6.5, "want": 6, "got": 4}]
    good, _ = checks_for(PARTS["a_placa"] + "\nEXPECTED_HOLES = [(HD, 4)]\n")
    assert good["holes_ok"].level == "ok"


def test_two_separate_solids_is_an_error():
    code = ("import cadquery as cq\n"
            "result = cq.Workplane('XY').box(10, 10, 10).union(\n"
            "    cq.Workplane('XY').center(30, 0).box(10, 10, 10))\n"
            "EXPECTED_BBOX = (40, 10, 10)\n")
    checks, info = checks_for(code)
    assert info["n_solids"] == 2
    assert checks["solid_invalid"].level == "error"


def test_weight_in_the_chosen_material():
    checks, info = checks_for(PARTS["d_caixa"], "pla")
    grams = info["volume_mm3"] / 1000 * 1.24
    assert checks["mass"].values["grams"] == pytest.approx(grams)
    assert f"{grams:.1f}".replace(".", ",") in checks["mass"].text("ca")[0]
