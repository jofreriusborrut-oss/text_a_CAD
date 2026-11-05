"""3D-printing analysis: orientation, supports, time and cost estimates."""
import pytest

from textacad import i18n, printability
from textacad.mesh import box_mesh

from . import shapes


def test_flat_plate_prints_flat_without_supports():
    data = printability.analyse(box_mesh((60, 40, 5)), "petg")
    best = data["best"]
    assert best["up"] in ("+z", "-z") and best["height_mm"] == 5
    assert best["support_area_mm2"] == 0 and best["bed_area_mm2"] == pytest.approx(2400)
    assert data["notes"] == ["no_support"]
    assert all(p["fits"] for p in data["printers"])
    est = data["estimate"]
    # 5800 mm2 of surface x 1.2 mm of shell = 6960 mm3, plus 20 % of the remaining 5040 mm3.
    assert est["printed_volume_cm3"] == pytest.approx(7.97, abs=0.005)
    assert est["mass_g"] == pytest.approx(10.1, abs=0.05) and est["solid_mass_g"] == pytest.approx(15.2, abs=0.05)
    assert est["time_minutes"] == 22
    assert est["material_cost_eur"] == pytest.approx(0.22, abs=0.005)


def test_bracket_is_not_printed_upside_down():
    data = printability.analyse(shapes.l_bracket(), "pla")
    by_up = {o["up"]: o for o in data["orientations"]}
    assert data["best"]["support_area_mm2"] == 0
    assert by_up["-z"]["support_area_mm2"] > 1000         # base in the air: needs support
    assert by_up["+z"]["support_area_mm2"] == 0 and by_up["+z"]["bed_area_mm2"] == pytest.approx(1200)
    assert data["orientations"][-1]["up"] in ("-z", "-x")  # the two upside-down ways come last
    assert "weak_between_layers" not in data["notes"]       # PLA bonds well between layers


def test_tall_tower_is_laid_down():
    data = printability.analyse(box_mesh((10, 10, 120)))
    assert data["best"]["height_mm"] == 10 and "tall_and_thin" not in data["notes"]


def test_too_big_for_desktop_printers():
    data = printability.analyse(box_mesh((400, 400, 10)))
    assert "too_big" in data["notes"] and not any(p["fits"] for p in data["printers"])
    assert printability.fits((200, 150), 100, (220, 220, 250))
    assert not printability.fits((230, 150), 100, (220, 220, 250))
    assert not printability.fits((215, 215), 100, (220, 210, 250))
    assert printability.fits((205, 215), 100, (220, 210, 250))    # the footprint can be turned 90 degrees
    assert not printability.fits((100, 100), 260, (220, 210, 250))


def test_small_contact_and_weak_layers_are_flagged():
    data = printability.analyse(box_mesh((8, 8, 8)), "abs")
    assert "small_bed_contact" in data["notes"] and "weak_between_layers" in data["notes"]


def test_machined_material_has_no_print_estimate():
    data = printability.analyse(box_mesh((20, 20, 20)), "al6061")
    assert data["estimate"] is None and data["material"]["process"] == "cnc"


def test_every_note_has_a_text():
    for code in ("no_support", "needs_support", "small_bed_contact", "tall_and_thin", "weak_between_layers", "too_big"):
        assert set(i18n.PRINT_NOTES[code]) == {"en", "ca", "es"}
