"""Every text exists in English, Catalan and Spanish."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from textacad import i18n
from textacad.checks import Check

STRINGS_JS = Path(__file__).resolve().parent.parent / "textacad" / "static" / "strings.js"

EXAMPLE_VALUES = {
    "solid_ok": {},
    "solid_invalid": {"solid_problems": ["brep_invalid", "n_solids", "not_watertight"], "n_solids": 2},
    "size_ok": {"size": [60, 40, 5]},
    "size_rotated": {"size": [60, 40, 5], "expected": [40, 60, 5]},
    "size_mismatch": {"size": [60, 40, 5], "expected": [60, 50, 5], "axes": [("Y", 40.0, 50.0)]},
    "size_unchecked": {"size": [60, 40, 5]},
    "holes_ok": {"found": [{"diameter": 6.6, "axis": "z", "count": 4}]},
    "holes_mismatch": {"found": [{"diameter": 6.6, "axis": "oblique", "count": 3}],
                       "hole_problems": [{"diameter": 6.6, "want": 4, "got": 3}]},
    "holes_listed": {"found": [{"diameter": 30.0, "axis": "x", "count": 1}]},
    "holes_none": {"found": []},
    "walls_ok": {"limit": 1.2, "thinnest": 2.0, "share": 0.0},
    "walls_thin": {"limit": 1.2, "thinnest": 0.8, "share": 31.4},
    "walls_unmeasured": {},
    "fit_ok": {},
    "fit_collision": {"volume": 85.3},
    "mass": {"volume": 12.0, "grams": 15.2, "density": 1.27, "material": "PETG"},
}


def test_language_helpers():
    assert i18n.lang_of("ca-ES") == "ca" and i18n.lang_of("fr") == "en" and i18n.lang_of(None) == "en"
    assert i18n.num(1.25, 1, "en") == "1.2" and i18n.num(1.25, 2, "ca") == "1,25"
    assert i18n.size_text([60, 40.5, 5], "es") == "60,0 × 40,5 × 5,0"
    assert i18n.pick(i18n.PRINT_NOTES, "does_not_exist", "ca") == "does_not_exist"


def test_all_tables_have_the_three_languages():
    for table in (i18n.CHECKS, i18n.SOLID_PROBLEMS, i18n.HOLE_PROBLEMS, i18n.SIM_WARNINGS,
                  i18n.MATERIAL_REASONS, i18n.MATERIAL_WARNINGS, i18n.PRINT_NOTES):
        for code, entry in table.items():
            assert set(entry) == set(i18n.LANGS), code


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_check_can_be_written(lang):
    assert set(EXAMPLE_VALUES) == set(i18n.CHECKS)
    for code, values in EXAMPLE_VALUES.items():
        title, detail = Check("info", code, values).text(lang)
        assert title and "{" not in title and "{" not in detail, code
    title, detail = Check("warning", "holes_mismatch", EXAMPLE_VALUES["holes_mismatch"]).text("ca")
    assert detail == "s'esperaven 4 × Ø6,6 però n'hi ha 3. Trobats a la peça: 3 × Ø6,6."
    assert Check("error", "solid_invalid", EXAMPLE_VALUES["solid_invalid"]).text("en")[1].startswith("The CAD kernel")


def test_interface_strings_have_the_same_keys_in_every_language():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    script = (
        "const src = require('fs').readFileSync(process.argv[1], 'utf8').replace('export const STRINGS', 'const STRINGS');"
        "const S = new Function(src + '; return STRINGS;')();"
        "console.log(JSON.stringify(Object.fromEntries(Object.entries(S).map(([k, v]) => [k, Object.keys(v).sort()]))));"
    )
    out = subprocess.run([node, "-e", script, str(STRINGS_JS)], capture_output=True, text=True, check=True).stdout
    keys = json.loads(out)
    assert set(keys) == set(i18n.LANGS)
    assert keys["ca"] == keys["en"] and keys["es"] == keys["en"]
    assert len(keys["en"]) > 100


def test_material_names_follow_the_language():
    from textacad.materials import MATERIALS

    assert i18n.material_name("pc", "Polycarbonate (PC)", "ca") == "Policarbonat (PC)"
    assert i18n.material_name("al6061", "Aluminium 6061-T6", "es") == "Aluminio 6061-T6"
    assert i18n.material_name("pc", "Polycarbonate (PC)", "en") == "Polycarbonate (PC)"
    assert i18n.material_name("petg", "PETG", "ca") == "PETG"            # trade names do not change
    assert set(i18n.MATERIAL_NAMES) <= set(MATERIALS)                    # no name for a material that does not exist

