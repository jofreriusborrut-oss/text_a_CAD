import cadquery as cq

PARAMS = {
    "length": {"value": 60, "unit": "mm", "min": 30, "max": 200, "label": "Llargada (X)"},
    "width": {"value": 80, "unit": "mm", "min": 30, "max": 200, "label": "Amplada (Y)"},
    "thickness": {"value": 5, "unit": "mm", "min": 1, "max": 20, "label": "Gruix"},
    "hole_diameter": {"value": 6.5, "unit": "mm", "min": 2, "max": 15, "label": "Diàmetre dels forats"},
    "hole_edge_distance": {"value": 10, "unit": "mm", "min": 4, "max": 40, "label": "Distància dels forats a les vores"},
    "corner_radius": {"value": 4, "unit": "mm", "min": 0, "max": 20, "label": "Radi de les cantonades"},
}

L = PARAMS["length"]["value"]
W = PARAMS["width"]["value"]
T = PARAMS["thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]
E = PARAMS["hole_edge_distance"]["value"]
R = PARAMS["corner_radius"]["value"]

R = min(R, L / 2 - 0.5, W / 2 - 0.5)
E = min(max(E, HD / 2 + 1), L / 2 - HD / 2 - 1, W / 2 - HD / 2 - 1)

result = cq.Workplane("XY").box(L, W, T, centered=(True, True, False))
if R > 0:
    result = result.edges("|Z").fillet(R)
result = (
    result.faces(">Z").workplane()
    .rect(L - 2 * E, W - 2 * E, forConstruction=True).vertices()
    .hole(HD)
)

EXPECTED_BBOX = (L, W, T)
