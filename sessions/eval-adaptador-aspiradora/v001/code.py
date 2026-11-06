import cadquery as cq

PARAMS = {
    "small_od": {"value": 35, "unit": "mm", "min": 15, "max": 120, "label": "Diàmetre exterior extrem prim"},
    "large_od": {"value": 50, "unit": "mm", "min": 20, "max": 150, "label": "Diàmetre exterior extrem gros"},
    "total_length": {"value": 70, "unit": "mm", "min": 30, "max": 250, "label": "Llargada total"},
    "wall": {"value": 2.5, "unit": "mm", "min": 1.5, "max": 6, "label": "Gruix de paret"},
    "small_len": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Llargada tram prim"},
    "large_len": {"value": 20, "unit": "mm", "min": 5, "max": 100, "label": "Llargada tram gros"},
}

D1 = PARAMS["small_od"]["value"]
D2 = PARAMS["large_od"]["value"]
L = PARAMS["total_length"]["value"]
T = PARAMS["wall"]["value"]
L1 = PARAMS["small_len"]["value"]
L2 = PARAMS["large_len"]["value"]

# Keep the geometry valid for any slider combination.
D2 = max(D2, D1 + 1)
T = min(T, D1 / 2 - 1)
L1 = max(L1, 1)
L2 = max(L2, 1)
LC = max(L - L1 - L2, 5)           # conical section length
L = L1 + LC + L2

R1 = D1 / 2
R2 = D2 / 2

# Half profile (radius, z) revolved around the Z axis.
pts = [
    (R1 - T, 0), (R1, 0), (R1, L1), (R2, L1 + LC), (R2, L),
    (R2 - T, L), (R2 - T, L1 + LC), (R1 - T, L1),
]
result = cq.Workplane("XZ").polyline(pts).close().revolve(360, (0, 0, 0), (0, 1, 0))

EXPECTED_BBOX = (D2, D2, L)
EXPECTED_HOLES = [(D1 - 2 * T, 1), (D2 - 2 * T, 1)]
