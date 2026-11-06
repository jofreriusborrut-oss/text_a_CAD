import cadquery as cq

PARAMS = {
    "small_od": {"value": 35, "unit": "mm", "min": 15, "max": 120, "label": "Diàmetre exterior extrem prim"},
    "large_od": {"value": 50, "unit": "mm", "min": 20, "max": 150, "label": "Diàmetre exterior extrem gros"},
    "total_length": {"value": 70, "unit": "mm", "min": 30, "max": 250, "label": "Llargada total"},
    "wall": {"value": 2.5, "unit": "mm", "min": 1.5, "max": 6, "label": "Gruix de paret"},
    "small_len": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Llargada tram prim"},
    "large_len": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Llargada tram gros"},
    "flange_diameter": {"value": 70, "unit": "mm", "min": 30, "max": 200, "label": "Diàmetre de la pestanya"},
    "flange_thickness": {"value": 3, "unit": "mm", "min": 2, "max": 10, "label": "Gruix de la pestanya"},
    "flange_bcd": {"value": 60, "unit": "mm", "min": 30, "max": 180, "label": "Diàmetre del cercle de forats"},
    "flange_hole": {"value": 4.5, "unit": "mm", "min": 2, "max": 10, "label": "Diàmetre dels forats (M4 = 4,5)"},
    "flange_hole_count": {"value": 3, "unit": "count", "min": 2, "max": 8, "label": "Nombre de forats"},
}

D1 = PARAMS["small_od"]["value"]
D2 = PARAMS["large_od"]["value"]
L = PARAMS["total_length"]["value"]
T = PARAMS["wall"]["value"]
L1 = PARAMS["small_len"]["value"]
L2 = PARAMS["large_len"]["value"]
FD = PARAMS["flange_diameter"]["value"]
FT = PARAMS["flange_thickness"]["value"]
BCD = PARAMS["flange_bcd"]["value"]
HOLE = PARAMS["flange_hole"]["value"]
N = int(PARAMS["flange_hole_count"]["value"])

# Keep the geometry valid for any slider combination.
D2 = max(D2, D1 + 1)
T = min(T, D1 / 2 - 1)
L1 = max(L1, 1)
L2 = max(L2, 1)
LC = max(L - L1 - L2, 5)           # conical section length
L = L1 + LC + L2

R1 = D1 / 2
R2 = D2 / 2

FT = min(FT, L2)
HOLE = min(HOLE, 10)
FD = max(FD, D2 + 2 * HOLE + 4)
BCD = min(max(BCD, D2 + HOLE + 2), FD - HOLE - 2)

# Half profile (radius, z) revolved around the Z axis.
pts = [
    (R1 - T, 0), (R1, 0), (R1, L1), (R2, L1 + LC), (R2, L),
    (R2 - T, L), (R2 - T, L1 + LC), (R2 - T, L1),
]
pts = [
    (R1 - T, 0), (R1, 0), (R1, L1), (R2, L1 + LC), (R2, L),
    (R2 - T, L), (R2 - T, L1 + LC), (R1 - T, L1),
]
body = cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

# Outer flange at the large end (flush with the top face), bore kept open.
flange = (
    cq.Workplane("XY").workplane(offset=L - FT)
    .circle(FD / 2).circle(R2 - T).extrude(FT)
)
body = body.union(flange)

# Bolt holes through the flange.
holes = (
    cq.Workplane("XY").workplane(offset=L - FT - 0.01)
    .polarArray(BCD / 2, 0, 360, N).circle(HOLE / 2).extrude(FT + 0.02)
)
result = body.cut(holes)

EXPECTED_BBOX = (FD, FD, L)
EXPECTED_HOLES = [(D1 - 2 * T, 1), (D2 - 2 * T, 1), (HOLE, N)]
