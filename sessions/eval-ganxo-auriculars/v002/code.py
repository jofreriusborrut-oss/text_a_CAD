import cadquery as cq

PARAMS = {
    "plate_length": {"value": 75, "unit": "mm", "min": 40, "max": 120, "label": "Llargada de la placa (X)"},
    "plate_width": {"value": 38, "unit": "mm", "min": 20, "max": 80, "label": "Amplada de la placa i del ganxo (Y)"},
    "plate_thickness": {"value": 8, "unit": "mm", "min": 4, "max": 12, "label": "Gruix de la placa"},
    "total_height": {"value": 88, "unit": "mm", "min": 40, "max": 150, "label": "Alçada total"},
    "arm_thickness": {"value": 10, "unit": "mm", "min": 4, "max": 15, "label": "Gruix del braç i del bec"},
    "hook_depth": {"value": 50, "unit": "mm", "min": 20, "max": 100, "label": "Fons de la J (sortida)"},
    "lip_height": {"value": 32, "unit": "mm", "min": 10, "max": 60, "label": "Alçada del bec"},
    "screw_hole": {"value": 4.5, "unit": "mm", "min": 3, "max": 8, "label": "Forat del cargol de fusta"},
    "csk_diameter": {"value": 9, "unit": "mm", "min": 6, "max": 16, "label": "Diàmetre de l'avellanat cònic"},
    "hole_edge": {"value": 15, "unit": "mm", "min": 6, "max": 30, "label": "Distància del forat a l'extrem"},
}

L = PARAMS["plate_length"]["value"]
W = PARAMS["plate_width"]["value"]
T = PARAMS["plate_thickness"]["value"]
H = PARAMS["total_height"]["value"]
A = PARAMS["arm_thickness"]["value"]
D = PARAMS["hook_depth"]["value"]
LIP = PARAMS["lip_height"]["value"]
HD = PARAMS["screw_hole"]["value"]
CS = PARAMS["csk_diameter"]["value"]
HE = PARAMS["hole_edge"]["value"]

# Keep the geometry valid for any slider combination.
A = min(A, L / 4, W / 2)
T = min(T, H / 3)
D = max(D, A + 5)
LIP = max(min(LIP, H - T - A - 10), 2)
CS = min(max(CS, HD + 1), W - 4)
HD = min(HD, CS - 1)
CDEPTH = min((CS - HD) / 2, T - 2)      # 90 degree countersink depth
CS = HD + 2 * CDEPTH
HE = min(max(HE, CS / 2 + 2), (L - A - CS - 2) / 2)

# Mounting plate on top (against the underside of the desk), z = H-T .. H.
plate = cq.Workplane("XY").box(L, W, T, centered=(False, True, False)).translate((0, 0, H - T))
# Vertical arm at the +X end of the plate, hanging down to z = 0.
arm = cq.Workplane("XY").box(A, W, H, centered=(False, True, False)).translate((L - A, 0, 0))
# Bottom of the J, going outwards (+X).
bottom = cq.Workplane("XY").box(D + A, W, A, centered=(False, True, False)).translate((L - A, 0, 0))
# Lip at the end, going up.
lip = cq.Workplane("XY").box(A, W, A + LIP, centered=(False, True, False)).translate((L + D - A, 0, 0))

body = plate.union(arm).union(bottom).union(lip)

# Wood screw holes through the plate with a conical countersink from below.
xs = [HE, L - A - HE]
for x in xs:
    hole = cq.Workplane("XY").workplane(offset=H - T).center(x, 0).circle(HD / 2).extrude(T)
    cone = cq.Workplane("XY").add(
        cq.Solid.makeCone(CS / 2 + 0.01, HD / 2, CDEPTH + 0.01,
                          pnt=cq.Vector(x, 0, H - T - 0.01))
    )
    body = body.cut(hole).cut(cone)

result = body

EXPECTED_BBOX = (L + D, W, H)
EXPECTED_HOLES = [(HD, 2)]

LOAD_CASE = {
    "description": "Plate screwed under the desk with two wood screws, 30 N downwards on the bottom of the hook (headphones)",
    "fixed": [{"type": "box", "min": [0, -W / 2, H - 0.5], "max": [L, W / 2, H + 0.01]}],
    "loads": [{"region": {"type": "point", "center": [L + D / 2, 0, A / 2], "radius": 6}, "force": [0, 0, -30]}],
}
