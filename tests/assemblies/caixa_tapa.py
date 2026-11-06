import cadquery as cq

PARAMS = {
    "length": {"value": 80, "unit": "mm", "min": 30, "max": 250, "label": "Llargada exterior (X)"},
    "width": {"value": 50, "unit": "mm", "min": 25, "max": 250, "label": "Amplada exterior (Y)"},
    "height": {"value": 30, "unit": "mm", "min": 10, "max": 150, "label": "Alçada de la caixa (Z)"},
    "wall": {"value": 2, "unit": "mm", "min": 1.2, "max": 5, "label": "Gruix de paret i fons"},
    "lid_thickness": {"value": 3, "unit": "mm", "min": 1.5, "max": 10, "label": "Gruix de la tapa"},
    "lip_height": {"value": 4, "unit": "mm", "min": 1, "max": 15, "label": "Alçada del llavi de la tapa"},
    "clearance": {"value": 0.2, "unit": "mm", "min": 0, "max": 1, "label": "Joc entre tapa i caixa"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
H = PARAMS["height"]["value"]
T = PARAMS["wall"]["value"]
LT = PARAMS["lid_thickness"]["value"]
LIP = PARAMS["lip_height"]["value"]
GAP = PARAMS["clearance"]["value"]

T = min(T, L / 4, W / 4, H / 2)
LIP = min(LIP, H - T - 1)

# Box: open at the top, resting on z = 0.
box = cq.Workplane("XY").box(L, W, H, centered=(True, True, False)).faces(">Z").shell(-T)

# Lid: a plate on top of the box plus a lip that goes inside it with some clearance.
plate = cq.Workplane("XY").workplane(offset=H).box(L, W, LT, centered=(True, True, False))
lip = (
    cq.Workplane("XY").workplane(offset=H - LIP)
    .box(L - 2 * T - 2 * GAP, W - 2 * T - 2 * GAP, LIP, centered=(True, True, False))
)
lid = plate.union(lip)

result = {"caixa": box, "tapa": lid}

EXPECTED_BBOX = (L, W, H + LT)
