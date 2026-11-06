import cadquery as cq

PARAMS = {
    "plate_length": {"value": 60, "unit": "mm", "min": 40, "max": 120, "label": "Llargada de la placa (X)"},
    "plate_width": {"value": 30, "unit": "mm", "min": 20, "max": 80, "label": "Amplada de la placa i del ganxo (Y)"},
    "plate_thickness": {"value": 6, "unit": "mm", "min": 4, "max": 12, "label": "Gruix de la placa"},
    "total_height": {"value": 70, "unit": "mm", "min": 40, "max": 150, "label": "Alçada total"},
    "arm_thickness": {"value": 8, "unit": "mm", "min": 4, "max": 15, "label": "Gruix del braç i del bec"},
    "hook_depth": {"value": 40, "unit": "mm", "min": 20, "max": 100, "label": "Fons de la J (sortida)"},
    "lip_height": {"value": 25, "unit": "mm", "min": 10, "max": 60, "label": "Alçada del bec"},
    "screw_hole": {"value": 4.5, "unit": "mm", "min": 3, "max": 8, "label": "Forat del cargol (M4 = 4,5)"},
    "cbore_diameter": {"value": 9, "unit": "mm", "min": 6, "max": 16, "label": "Avellanat del cap del cargol"},
    "cbore_depth": {"value": 3, "unit": "mm", "min": 1, "max": 6, "label": "Fondària de l'avellanat"},
    "hole_edge": {"value": 12, "unit": "mm", "min": 6, "max": 30, "label": "Distància del forat a l'extrem"},
}

L = PARAMS["plate_length"]["value"]
W = PARAMS["plate_width"]["value"]
T = PARAMS["plate_thickness"]["value"]
H = PARAMS["total_height"]["value"]
A = PARAMS["arm_thickness"]["value"]
D = PARAMS["hook_depth"]["value"]
LIP = PARAMS["lip_height"]["value"]
HD = PARAMS["screw_hole"]["value"]
CB = PARAMS["cbore_diameter"]["value"]
CD = PARAMS["cbore_depth"]["value"]
HE = PARAMS["hole_edge"]["value"]

# Keep the geometry valid for any slider combination.
A = min(A, L / 4, W / 2)
T = min(T, H / 3)
D = max(D, A + 5)
LIP = max(min(LIP, H - T - A - 10), 2)
CB = min(max(CB, HD + 1), W - 4)
HD = min(HD, CB - 1)
CD = min(CD, T - 2)
HE = min(max(HE, CB / 2 + 2), (L - A - CB - 2) / 2)

# Mounting plate on top (against the underside of the desk), z = H-T .. H.
plate = cq.Workplane("XY").box(L, W, T, centered=(False, True, False)).translate((0, 0, H - T))
# Vertical arm at the +X end of the plate, hanging down to z = 0.
arm = cq.Workplane("XY").box(A, W, H, centered=(False, True, False)).translate((L - A, 0, 0))
# Bottom of the J, going outwards (+X).
bottom = cq.Workplane("XY").box(D + A, W, A, centered=(False, True, False)).translate((L - A, 0, 0))
# Lip at the end, going up.
lip = cq.Workplane("XY").box(A, W, A + LIP, centered=(False, True, False)).translate((L + D - A, 0, 0))

body = plate.union(arm).union(bottom).union(lip)

# Screw holes through the plate with counterbore from below.
xs = [HE, L - A - HE]
for x in xs:
    hole = cq.Workplane("XY").workplane(offset=H - T).center(x, 0).circle(HD / 2).extrude(T)
    cbore = cq.Workplane("XY").workplane(offset=H - T).center(x, 0).circle(CB / 2).extrude(CD)
    body = body.cut(hole).cut(cbore)

result = body

EXPECTED_BBOX = (L + D, W, H)
EXPECTED_HOLES = [(HD, 2), (CB, 2)]

LOAD_CASE = {
    "description": "Plate screwed under the desk, 20 N downwards on the bottom of the hook (headphones)",
    "fixed": [{"type": "box", "min": [0, -W / 2, H - 0.5], "max": [L, W / 2, H + 0.01]}],
    "loads": [{"region": {"type": "point", "center": [L + D / 2, 0, A / 2], "radius": 6}, "force": [0, 0, -20]}],
}
