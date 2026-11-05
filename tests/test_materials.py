"""Material data and the rule-based recommender."""
import pytest

from textacad import i18n
from textacad.materials import MATERIALS, UseCase, get_material, recommend, required_safety_factor


def test_data_is_sane():
    assert {"pla", "petg", "asa", "pa-cf", "tpu95a", "al6061", "al7075"} <= set(MATERIALS)
    for m in MATERIALS.values():
        assert m.E > 0 and 0 < m.nu < 0.5, m.id
        assert 0 < m.yield_strength <= m.tensile_strength, m.id
        assert 0.8 < m.density < 9 and m.max_service_temp > 30, m.id
        assert 0 < m.z_factor <= 1, m.id
        assert m.process in ("fdm", "sls", "cnc")
        if m.process == "cnc":
            assert m.z_factor == 1                      # metals are the same in every direction
        assert set(m.notes) == {"en", "ca", "es"} and all(m.notes.values()), m.id
        assert m.weak_axis_strength == pytest.approx(m.yield_strength * m.z_factor)
    assert get_material("PETG").id == "petg"
    with pytest.raises(KeyError):
        get_material("unobtainium")


def test_hot_place_with_fuel_rules_out_pla_and_petg():
    use = UseCase.from_dict({"process": "fdm", "max_temp_c": 90, "outdoor": "yes", "fluids": True,
                             "vibration": "si"})
    assert use.processes == ("fdm",) and use.outdoor and use.fluids and use.vibration and not use.flexible
    ranked = recommend(use)
    by_id = {r.material.id: r for r in ranked}
    assert not by_id["pla"].suitable and "too_hot" in by_id["pla"].warnings
    assert not by_id["petg"].suitable and "too_hot" in by_id["petg"].warnings
    assert "process_unavailable" in by_id["al6061"].warnings and not by_id["al6061"].suitable
    best = ranked[0]
    assert best.suitable and best.material.process == "fdm" and best.material.max_service_temp >= 90
    flags = [r.suitable for r in ranked]
    assert flags == sorted(flags, reverse=True)          # every unsuitable material comes after the suitable ones


def test_stress_from_the_simulation_gives_safety_factors():
    use = UseCase(processes=("fdm", "cnc"), vibration=True, stress_mpa=12.0)
    by_id = {r.material.id: r for r in recommend(use)}
    petg = by_id["petg"]
    assert petg.safety_factor == pytest.approx(45 * 0.70 / 12)
    assert petg.required_factor == required_safety_factor(get_material("petg"), use) == 4.0
    assert "low_safety_factor" in petg.warnings and petg.suitable
    alu = by_id["al6061"]
    assert alu.required_factor == 3.0 and "strong_enough" in alu.reasons
    broken = {r.material.id: r for r in recommend(UseCase(stress_mpa=80.0))}
    assert not broken["pla"].suitable and "breaks" in broken["pla"].warnings


def test_flexible_part_needs_tpu():
    ranked = recommend(UseCase(flexible=True))
    assert ranked[0].material.id == "tpu95a" and ranked[0].suitable
    assert all(not r.suitable for r in ranked[1:])
    rigid = {r.material.id: r for r in recommend(UseCase())}
    assert "too_flexible" in rigid["tpu95a"].warnings


def test_use_case_from_the_note():
    use = UseCase.from_dict({"process": "unknown", "max_temp_c": "unknown", "outdoor": False})
    assert use.processes == ("fdm",) and use.max_temp_c is None
    assert UseCase.from_dict({"processes": ["cnc", "sls"]}).processes == ("cnc", "sls")
    assert UseCase.from_dict(None) == UseCase()


def test_every_reason_and_warning_has_a_text():
    uses = [UseCase(), UseCase(flexible=True, stress_mpa=500), UseCase(processes=("cnc",), max_temp_c=100),
            UseCase(processes=("fdm", "sls", "cnc"), max_temp_c=75, outdoor=True, fluids=True, vibration=True,
                    stress_mpa=20)]
    seen = set()
    for use in uses:
        for rec in recommend(use):
            for code in rec.reasons:
                assert set(i18n.MATERIAL_REASONS[code]) == {"en", "ca", "es"}
            for code in rec.warnings:
                assert set(i18n.MATERIAL_WARNINGS[code]) == {"en", "ca", "es"}
            seen.update(rec.reasons + rec.warnings)
    assert {"too_hot", "breaks", "low_safety_factor", "strong_enough", "uv_good", "easy"} <= seen
