"""Reference component catalogue: matching and user components."""
import pytest

from textacad import catalog
from textacad.catalog_data import COMPONENTS


def ids(text, **kw):
    return [c["id"] for c in catalog.find_components(text, **kw)]


def test_ids_are_unique_and_entries_complete():
    seen = [c["id"] for c in COMPONENTS]
    assert len(seen) == len(set(seen))
    for c in COMPONENTS:
        assert c["name"] and c["category"] and c["match"] and c["confidence"] and c["source"]
        assert all(isinstance(p, (list, tuple)) and p for p in c["match"])
        assert all(w == w.lower() for p in c["match"] for w in p)


def test_metric_sizes():
    assert ids("Placa amb 4 forats M5 i dos cargols M3x12") == ["metric-m5", "metric-m3"] or \
        set(ids("Placa amb 4 forats M5 i dos cargols M3x12")) == {"metric-m5", "metric-m3"}
    assert "metric-m2.5" in ids("separadors per a cargols M2,5")
    m6 = next(c for c in COMPONENTS if c["id"] == "metric-m6")
    assert m6["dims"]["clearance_hole_medium"] == 6.6
    assert m6["dims"]["cap_screw_head_diameter"] == 10.0
    assert m6["dims"]["tap_drill"] == 5.0
    assert m6["dims"]["hex_nut_across_flats"] == 10.0


def test_bearing_needs_context():
    assert ids("tub de 625 mm de llarg") == []
    assert ids("allotjament per a un rodament 625") == ["bearing-625"]
    assert ids("seat for a 608ZZ") == ["bearing-608"]
    b = catalog.find_components("coixinet 6204")[0]
    assert (b["dims"]["bore"], b["dims"]["outer_diameter"], b["dims"]["width"]) == (20, 47, 14)


def test_motor_and_board():
    assert "nema17" in ids("Suport per a motor NEMA 17")
    assert "nema17" in ids("bracket for a nema17 stepper")
    assert ids("caixa per a una Raspberry Pi 4") == ["raspberry-pi"]
    assert ids("case for a Raspberry Pi Pico") == ["raspberry-pi-pico"]
    assert ids("profile 2020 corner bracket") [0] == "profile-2020"
    assert ids("fet l'any 2020") == []


def test_fork_sensor_request_brings_the_guide_and_the_sensor():
    found = ids("Suport per a un sensor de recorregut lineal AiM Eclipse de 150 mm a la forquilla "
                "de la moto de MotoStudent, tub de 52 mm, amb cargol M5")
    assert "aim-eclipse-150" in found
    assert "guide-fork-travel-sensor" in found
    assert "metric-m5" in found
    assert "aim-eclipse-family" not in found            # the specific model hides the family entry
    spec = next(c for c in COMPONENTS if c["id"] == "aim-eclipse-150")
    assert spec["dims"]["retracted_mounting_distance"] == 265
    assert spec["dims"]["body_length"] == 231


def test_sensor_without_travel_gives_the_family():
    found = ids("suport per al potenciòmetre AiM de la suspensió")
    assert "aim-eclipse-family" in found


def test_user_components(tmp_path):
    path = tmp_path / "catalog_user.json"
    entry = catalog.save_user_component(
        "Sensor Variohm ELPM 100", {"Body diameter": 12.7, "stroke": 100}, notes="rod ends M5",
        keywords=["variohm elpm"], path=path)
    assert entry["id"] == "user-sensor-variohm-elpm-100"
    assert entry["dims"] == {"body_diameter": 12.7, "stroke": 100}
    assert ids("suport per al Variohm ELPM", path=path) == ["user-sensor-variohm-elpm-100"]
    assert catalog.search("variohm", path=path)[0]["id"] == entry["id"]
    assert catalog.delete_user_component(entry["id"], path=path)
    assert ids("suport per al Variohm ELPM", path=path) == []


def test_bad_user_component_is_rejected(tmp_path):
    with pytest.raises(catalog.CatalogError):
        catalog.save_user_component("x", {"d": 1}, path=tmp_path / "c.json")
    with pytest.raises(catalog.CatalogError):
        catalog.save_user_component("Good name", {}, path=tmp_path / "c.json")


def test_describe_is_compact_text():
    text = catalog.describe(next(c for c in COMPONENTS if c["id"] == "nema17"))
    assert "bolt_square = 31.0" in text and text.startswith("- NEMA 17")


def test_search_browser():
    assert catalog.search("bearing")[0]["category"] == "bearing"
    assert any(c["id"] == "pg-sls130" for c in catalog.search("penny"))
    assert len(catalog.search("")) >= len(COMPONENTS)
