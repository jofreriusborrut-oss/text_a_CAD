"""The technical sheet (HTML) of a version."""
from textacad import checks, printability, report
from textacad.materials import get_material
from textacad.mesh import box_mesh, dump_stl
from textacad.session import Version
from textacad.simulate import run_simulation


def make_version():
    info = {"is_valid": True, "n_solids": 1, "volume_mm3": 12000.0, "bbox": {"size": [60.0, 40.0, 5.0]},
            "expected_bbox": [60.0, 40.0, 5.0], "center_of_mass": [0.0, 0.0, 2.5],
            "holes": [{"diameter": 6.6, "axis": "z", "count": 4}], "expected_holes": [[6.6, 4]]}
    params = {"length": {"value": 60, "unit": "mm", "min": 20, "max": 200, "label": "Llargada <X>"},
              "holes": {"value": 4, "unit": "count", "min": 0, "max": 8, "label": "Forats"}}
    note = {"title": "placa", "summary": "Placa de 60 × 40 × 5 mm amb 4 forats M6.",
            "assumptions": ["Forats M6 amb joc mitjà: 6,6 mm."], "use": {"process": "fdm"}}
    return Version(number=2, instruction="Fes-la de 5 mm", parent=1, base_code="", code="", params=params,
                   values={"length": 60, "holes": 4}, info=info, note=note)


def build(lang, with_simulation=True):
    mesh = box_mesh((60, 40, 5), origin=(-30, -20, 0))
    version = make_version()
    material = get_material("petg")
    simulation = None
    if with_simulation:
        case = {"description": "Held on the left, 20 N down on the right",
                "fixed": [{"type": "side", "side": "-x"}],
                "loads": [{"region": {"type": "side", "side": "+x"}, "force": [0, 0, -20]}]}
        simulation = run_simulation(mesh, case, material, "draft").summary()
    check_list = [c.as_dict(lang) for c in checks.run_checks(version.info, dump_stl(mesh), material)]
    return report.build(title="Placa <script>alert(1)</script>", version=version,
                        history=["Placa de 60x40x3", "Fes-la de 5 mm"], checks=check_list, material=material,
                        simulation=simulation, print_data=printability.analyse(mesh, material),
                        image="data:image/png;base64,AAAA", lang=lang)


def test_sheet_in_catalan_has_every_section():
    html = build("ca")
    assert html.startswith("<!doctype html><html lang='ca'>")
    for text in ("Fitxa tècnica", "Versió 2", "Què es va demanar", "Fes-la de 5 mm", "Suposicions per confirmar",
                 "Paràmetres", "Llargada &lt;X&gt;", "60,00 × 40,00 × 5,00 mm", "12,00 cm³", "4 × Ø6,6 (Z)",
                 "Els forats coincideixen amb la descripció", "Material: PETG", "Simulació de tensions",
                 "Tensió màxima (von Mises)", "Impressió 3D", "STEP per a SolidWorks"):
        assert text in html, text
    assert "<script>" not in html and "&lt;script&gt;" in html          # user text is escaped
    assert "<img class='shot' src='data:image/png;base64,AAAA'" in html
    assert "<td>4 </td>" in html                                        # counts have no unit


def test_sheet_in_english_and_spanish():
    en = build("en", with_simulation=False)
    assert "Technical sheet" in en and "Stress simulation" not in en and "60.00 × 40.00 × 5.00 mm" in en
    es = build("es")
    assert "Ficha técnica" in es and "Simulación de tensiones" in es and "Impresión 3D" in es


def test_unknown_language_falls_back_to_english():
    assert "Technical sheet" in build("fr", with_simulation=False)
