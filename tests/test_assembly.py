"""Assemblies: `result = {"name": solid, ...}` gives one component per part.

These tests do NOT call Claude.
"""
import io
import zipfile
from pathlib import Path

import pytest

from textacad.checks import run_checks
from textacad.generator import _problems
from textacad.regenerate import regenerate
from textacad.sandbox import run_code

BOX_AND_LID = (Path(__file__).parent / "assemblies" / "caixa_tapa.py").read_text(encoding="utf-8")

TWO_BLOCKS = (
    "import cadquery as cq\n"
    "a = cq.Workplane('XY').box(20, 20, 10, centered=(True, True, False))\n"
    "b = cq.Workplane('XY').workplane(offset={z}).box(10, 10, 10, centered=(True, True, False))\n"
    "result = {{'base': a, {name!r}: b}}\n"
    "EXPECTED_BBOX = (20, 20, {z} + 10)\n"
)


def test_assembly_exports_every_part():
    run = run_code(BOX_AND_LID)
    try:
        assert run.ok, run.error
        info = run.info
        assert info["assembly"] and [p["name"] for p in info["parts"]] == ["caixa", "tapa"]
        assert all(p["n_solids"] == 1 and p["is_valid"] for p in info["parts"])
        assert info["overlaps"] == []                       # the lip has clearance
        assert info["bbox"]["size"] == pytest.approx([80, 50, 33], abs=0.1)
        assert info["volume_mm3"] == pytest.approx(sum(p["volume_mm3"] for p in info["parts"]))
        assert _problems(BOX_AND_LID, run) is None
        assert run.step_path.stat().st_size > 1000 and run.stl_path.stat().st_size > 1000
        for name in ("caixa", "tapa"):
            assert (run.job_dir / "parts" / f"{name}.step").stat().st_size > 1000
            assert (run.job_dir / "parts" / f"{name}.stl").stat().st_size > 1000
        if info["step_kind"] == "assembly":                 # component names end up in the STEP
            step = run.step_path.read_text(encoding="utf-8", errors="replace")
            assert "caixa" in step and "tapa" in step
        names = zipfile.ZipFile(io.BytesIO(run.parts_zip())).namelist()
        assert set(names) == {"conjunt.step", "peces/caixa.step", "peces/caixa.stl",
                              "peces/tapa.step", "peces/tapa.stl"}
    finally:
        run.cleanup()


def test_single_part_has_no_zip():
    run = run_code((Path(__file__).parent / "parts" / "a_placa.py").read_text(encoding="utf-8"))
    try:
        assert run.ok and not run.info.get("assembly") and run.parts_zip() is None
    finally:
        run.cleanup()


def test_assembly_checks_are_clean():
    run = run_code(BOX_AND_LID)
    try:
        checks = run_checks(run.info, run.stl_path.read_bytes())
    finally:
        run.cleanup()
    assert not [c for c in checks if c.level in ("error", "warning")], checks
    assert any("Conjunt de 2 peces" in c.title for c in checks)


def test_touching_parts_are_fine_but_overlapping_ones_are_reported():
    touching = run_code(TWO_BLOCKS.format(z=10, name="bloc"))
    overlapping = run_code(TWO_BLOCKS.format(z=5, name="bloc"))
    try:
        assert touching.ok and touching.info["overlaps"] == []
        assert overlapping.ok
        (o,) = overlapping.info["overlaps"]
        assert {o["a"], o["b"]} == {"base", "bloc"} and o["volume_mm3"] == pytest.approx(500, rel=0.01)
        assert "occupy the same space" in _problems("", overlapping)      # sent back to Claude
        checks = run_checks(overlapping.info, overlapping.stl_path.read_bytes())
        assert any(c.level == "warning" and "trepitgen" in c.title for c in checks)
    finally:
        touching.cleanup()
        overlapping.cleanup()


def test_bad_part_name_is_an_error():
    run = run_code(TWO_BLOCKS.format(z=10, name="tapa superior"))
    assert not run.ok and "not valid" in run.error
    run.cleanup()


def test_sliders_rebuild_the_whole_assembly():
    out = regenerate(BOX_AND_LID, {"height": 40})
    assert out["ok"], out["error"]
    assert out["info"]["bbox"]["size"][2] == pytest.approx(43, abs=0.1)
    assert out["zip"] and len(out["info"]["parts"]) == 2
