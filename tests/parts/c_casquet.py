import cadquery as cq

PARAMS = {
    "outer_diameter": {"value": 20, "unit": "mm", "min": 5, "max": 150, "label": "Diàmetre exterior"},
    "inner_diameter": {"value": 8, "unit": "mm", "min": 1, "max": 140, "label": "Diàmetre interior"},
    "height": {"value": 15, "unit": "mm", "min": 2, "max": 150, "label": "Alçada"},
    "chamfer": {"value": 1, "unit": "mm", "min": 0, "max": 5, "label": "Xamfrà"},
}

OD = PARAMS["outer_diameter"]["value"]
ID = PARAMS["inner_diameter"]["value"]
H = PARAMS["height"]["value"]
C = PARAMS["chamfer"]["value"]

ID = min(ID, OD - 2)
C = min(C, (OD - ID) / 4, H / 4)

result = cq.Workplane("XY").circle(OD / 2).circle(ID / 2).extrude(H)
if C > 0:
    # All four circular edges (outer and inner, top and bottom).
    result = result.edges().chamfer(C)

EXPECTED_BBOX = (OD, OD, H)
