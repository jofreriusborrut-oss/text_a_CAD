import cadquery as cq

PARAMS = {
    "length": {"value": 100, "unit": "mm", "min": 20, "max": 300, "label": "Llargada exterior (X)"},
    "width": {"value": 60, "unit": "mm", "min": 20, "max": 300, "label": "Amplada exterior (Y)"},
    "height": {"value": 40, "unit": "mm", "min": 5, "max": 200, "label": "Alçada exterior (Z)"},
    "wall": {"value": 2, "unit": "mm", "min": 0.8, "max": 8, "label": "Gruix de paret i fons"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
H = PARAMS["height"]["value"]
T = PARAMS["wall"]["value"]

T = min(T, L / 4, W / 4, H / 2)

result = (
    cq.Workplane("XY")
    .box(L, W, H, centered=(True, True, False))
    .faces(">Z").shell(-T)
)

EXPECTED_BBOX = (L, W, H)
