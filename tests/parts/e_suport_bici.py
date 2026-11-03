import cadquery as cq

PARAMS = {
    "plate_height": {"value": 120, "unit": "mm", "min": 60, "max": 250, "label": "Alçada de la placa (Y)"},
    "plate_width": {"value": 60, "unit": "mm", "min": 30, "max": 150, "label": "Amplada de la placa (X)"},
    "plate_thickness": {"value": 6, "unit": "mm", "min": 3, "max": 15, "label": "Gruix de la placa"},
    "hole_diameter": {"value": 6.6, "unit": "mm", "min": 3, "max": 12, "label": "Forats (M6 = 6,6)"},
    "hole_edge_distance": {"value": 12, "unit": "mm", "min": 6, "max": 40, "label": "Distància dels forats a la vora"},
    "hook_length": {"value": 80, "unit": "mm", "min": 30, "max": 200, "label": "Llargada del ganxo"},
    "hook_width": {"value": 20, "unit": "mm", "min": 8, "max": 60, "label": "Amplada del ganxo (X)"},
    "hook_section": {"value": 15, "unit": "mm", "min": 6, "max": 40, "label": "Cantell del ganxo (Y)"},
    "lip_height": {"value": 20, "unit": "mm", "min": 0, "max": 60, "label": "Alçada del topall final"},
    "lip_thickness": {"value": 8, "unit": "mm", "min": 4, "max": 30, "label": "Gruix del topall final"},
}

PH = PARAMS["plate_height"]["value"]
PW = PARAMS["plate_width"]["value"]
PT = PARAMS["plate_thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]
E = PARAMS["hole_edge_distance"]["value"]
HL = PARAMS["hook_length"]["value"]
HW = PARAMS["hook_width"]["value"]
HS = PARAMS["hook_section"]["value"]
LH = PARAMS["lip_height"]["value"]
LT = PARAMS["lip_thickness"]["value"]

HW = min(HW, PW - 4)
E = min(max(E, HD / 2 + 2), PH / 4)
LT = min(LT, HL / 2)
LH = min(LH, PH / 2 - HS / 2 - 2)

# Wall plate lying on XY (back of the plate at z = 0, it goes against the wall).
plate = cq.Workplane("XY").box(PW, PH, PT, centered=(True, True, False))

# 3 mounting holes: two at the top corners, one at the bottom centre.
pts = [(-PW / 2 + E, PH / 2 - E), (PW / 2 - E, PH / 2 - E), (0, -PH / 2 + E)]
plate = plate.faces(">Z").workplane().pushPoints(pts).hole(HD)

# Hook: a bar sticking out of the plate (along +Z), centred on the plate,
# with an upward lip at the end so the frame cannot slide off.
bar = (
    cq.Workplane("XY").workplane(offset=PT)
    .rect(HW, HS).extrude(HL)
)
lip = (
    cq.Workplane("XY").workplane(offset=PT + HL - LT)
    .center(0, LH / 2)              # spans from y = -HS/2 up to y = HS/2 + LH
    .rect(HW, HS + LH).extrude(LT)
)
result = plate.union(bar).union(lip)
result = result.faces(">Z").edges().fillet(min(2, LT / 4))

EXPECTED_BBOX = (PW, PH, PT + HL)
