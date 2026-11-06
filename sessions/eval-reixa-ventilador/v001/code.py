import cadquery as cq

PARAMS = {
    "frame_size": {"value": 80, "unit": "mm", "min": 40, "max": 200, "label": "Mida del marc (X i Y)"},
    "thickness": {"value": 3, "unit": "mm", "min": 1, "max": 10, "label": "Gruix"},
    "hole_diameter": {"value": 4.5, "unit": "mm", "min": 2, "max": 8, "label": "Diàmetre dels forats de fixació"},
    "hole_spacing": {"value": 71.5, "unit": "mm", "min": 20, "max": 180, "label": "Distància entre centres dels forats"},
    "opening_diameter": {"value": 76, "unit": "mm", "min": 20, "max": 190, "label": "Diàmetre de l'obertura"},
    "ring_count": {"value": 3, "unit": "count", "min": 1, "max": 8, "label": "Nombre d'anells"},
    "ring_width": {"value": 1.5, "unit": "mm", "min": 0.8, "max": 5, "label": "Amplada dels anells"},
    "spoke_width": {"value": 2, "unit": "mm", "min": 0.8, "max": 6, "label": "Amplada dels radis"},
}

L = PARAMS["frame_size"]["value"]
T = PARAMS["thickness"]["value"]
HD = PARAMS["hole_diameter"]["value"]
HS = PARAMS["hole_spacing"]["value"]
OD = PARAMS["opening_diameter"]["value"]
N = int(PARAMS["ring_count"]["value"])
RW = PARAMS["ring_width"]["value"]
SW = PARAMS["spoke_width"]["value"]

# Keep the geometry valid for any slider combination.
HD = min(HD, L / 4)
HS = min(HS, L - HD - 2)
OD = min(OD, L - 4)
R = OD / 2
RW = min(RW, R / (N + 1) * 0.8)
SW = min(SW, R)

# Frame with circular opening.
frame = cq.Workplane("XY").box(L, L, T, centered=(True, True, False))
frame = frame.cut(cq.Workplane("XY").circle(R).extrude(T))

# Concentric rings.
grille = None
for i in range(1, N + 1):
    r = R * i / (N + 1)
    ring = cq.Workplane("XY").circle(r + RW / 2).circle(r - RW / 2).extrude(T)
    grille = ring if grille is None else grille.union(ring)

# Four spokes (two crossing bars).
bar1 = cq.Workplane("XY").box(2 * R + 2, SW, T, centered=(True, True, False))
bar2 = cq.Workplane("XY").box(SW, 2 * R + 2, T, centered=(True, True, False))
grille = grille.union(bar1).union(bar2)

# Trim the grille so it overlaps the frame slightly and does not stick out.
trim = cq.Workplane("XY").circle(R + 0.5).extrude(T)
grille = grille.intersect(trim)

body = frame.union(grille)

# Mounting holes in a square.
pts = [(sx * HS / 2, sy * HS / 2) for sx in (-1, 1) for sy in (-1, 1)]
holes = cq.Workplane("XY").pushPoints(pts).circle(HD / 2).extrude(T)
result = body.cut(holes)

EXPECTED_BBOX = (L, L, T)
EXPECTED_HOLES = [(HD, 4)]
