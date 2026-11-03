import cadquery as cq

PARAMS = {
    "leg_a": {"value": 40, "unit": "mm", "min": 15, "max": 150, "label": "Llargada ala horitzontal"},
    "leg_b": {"value": 40, "unit": "mm", "min": 15, "max": 150, "label": "Llargada ala vertical"},
    "width": {"value": 30, "unit": "mm", "min": 10, "max": 100, "label": "Amplada"},
    "thickness": {"value": 4, "unit": "mm", "min": 1.5, "max": 12, "label": "Gruix"},
    "hole_diameter": {"value": 5, "unit": "mm", "min": 2, "max": 12, "label": "Diàmetre dels forats"},
}

A = PARAMS["leg_a"]["value"]
B = PARAMS["leg_b"]["value"]
W = PARAMS["width"]["value"]
T = PARAMS["thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]

T = min(T, A / 3, B / 3)
HD = min(HD, W / 2 - 2, (A - T) - 2, (B - T) - 2)

# L profile in XZ (horizontal leg along X, vertical leg along Z), extruded along Y.
profile = [(0, 0), (A, 0), (A, T), (T, T), (T, B), (0, B)]
body = cq.Workplane("XZ").polyline(profile).close().extrude(W / 2, both=True)

# Two holes in each leg, centred on the free part of the leg, at 1/4 and 3/4 of the width.
x_h = (A + T) / 2
z_v = (B + T) / 2
ys = [-W / 4, W / 4]
holes_h = cq.Workplane("XY").pushPoints([(x_h, y) for y in ys]).circle(HD / 2).extrude(T)
holes_v = cq.Workplane("YZ").pushPoints([(y, z_v) for y in ys]).circle(HD / 2).extrude(T)
result = body.cut(holes_h).cut(holes_v)

EXPECTED_BBOX = (A, W, B)
