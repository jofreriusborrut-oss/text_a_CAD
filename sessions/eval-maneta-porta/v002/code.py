import cadquery as cq

PARAMS = {
    "bar_length": {"value": 140, "unit": "mm", "min": 60, "max": 300, "label": "Llargada de la barra (X)"},
    "bar_width": {"value": 20, "unit": "mm", "min": 10, "max": 50, "label": "Amplada de la barra (Y)"},
    "bar_thickness": {"value": 12, "unit": "mm", "min": 8, "max": 40, "label": "Gruix de la barra (Z)"},
    "bar_radius": {"value": 3, "unit": "mm", "min": 0, "max": 5, "label": "Radi de les arestes"},
    "foot_height": {"value": 15, "unit": "mm", "min": 8, "max": 60, "label": "Alçada dels peus"},
    "foot_diameter": {"value": 12, "unit": "mm", "min": 8, "max": 20, "label": "Diàmetre dels peus"},
    "foot_spacing": {"value": 96, "unit": "mm", "min": 20, "max": 250, "label": "Distància entre peus"},
    "tap_hole": {"value": 3.3, "unit": "mm", "min": 2, "max": 6, "label": "Forat roscat M4 (broca 3,3)"},
    "tap_depth": {"value": 10, "unit": "mm", "min": 4, "max": 40, "label": "Fondària del forat"},
}

L = PARAMS["bar_length"]["value"]
W = PARAMS["bar_width"]["value"]
T = PARAMS["bar_thickness"]["value"]
R = PARAMS["bar_radius"]["value"]
FH = PARAMS["foot_height"]["value"]
FD = PARAMS["foot_diameter"]["value"]
SP = PARAMS["foot_spacing"]["value"]
HD = PARAMS["tap_hole"]["value"]
HDEP = PARAMS["tap_depth"]["value"]

R = min(R, T / 2 - 0.1, W / 2 - 0.1)
FD = min(FD, W - 2 * R - 0.5)
FD = max(FD, 4)
HD = min(HD, FD - 3)
SP = min(SP, L - FD - 2 * R)
HDEP = min(HDEP, FH - 2)

bar = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
if R > 0:
    bar = bar.edges().fillet(R)
bar = bar.translate((0, 0, FH))

pts = [(-SP / 2, 0), (SP / 2, 0)]
feet = cq.Workplane("XY").pushPoints(pts).circle(FD / 2).extrude(FH + 1)
body = bar.union(feet)

holes = cq.Workplane("XY").pushPoints(pts).circle(HD / 2).extrude(HDEP)
result = body.cut(holes)

EXPECTED_BBOX = (L, W, FH + T)
EXPECTED_HOLES = [(HD, 2)]
