import cadquery as cq

PARAMS = {
    "board_length": {"value": 68.6, "unit": "mm", "min": 60, "max": 80, "label": "Llargada de la placa"},
    "board_width": {"value": 53.4, "unit": "mm", "min": 45, "max": 65, "label": "Amplada de la placa"},
    "board_thickness": {"value": 1.6, "unit": "mm", "min": 1, "max": 2.5, "label": "Gruix de la placa"},
    "clearance": {"value": 1, "unit": "mm", "min": 0, "max": 3, "label": "Joc placa-paret"},
    "wall": {"value": 2, "unit": "mm", "min": 1.5, "max": 5, "label": "Gruix de paret i fons"},
    "inner_height": {"value": 30, "unit": "mm", "min": 20, "max": 60, "label": "Alçada interior"},
    "standoff_height": {"value": 5, "unit": "mm", "min": 3, "max": 12, "label": "Alçada de les torretes"},
    "standoff_diameter": {"value": 6, "unit": "mm", "min": 5, "max": 10, "label": "Diàmetre de les torretes"},
    "standoff_hole": {"value": 2.5, "unit": "mm", "min": 1.5, "max": 3.2, "label": "Forat de les torretes"},
    "usb_y": {"value": 38.5, "unit": "mm", "min": 5, "max": 50, "label": "Centre USB (Y des del cantó)"},
    "usb_width": {"value": 12, "unit": "mm", "min": 8, "max": 20, "label": "Amplada obertura USB"},
    "power_y": {"value": 7.5, "unit": "mm", "min": 5, "max": 50, "label": "Centre alimentació (Y)"},
    "power_width": {"value": 9, "unit": "mm", "min": 6, "max": 16, "label": "Amplada obertura alimentació"},
    "port_height": {"value": 11, "unit": "mm", "min": 6, "max": 16, "label": "Alçada dels connectors"},
    "port_margin": {"value": 1, "unit": "mm", "min": 0, "max": 2, "label": "Joc de les obertures"},
}

BL = PARAMS["board_length"]["value"]
BW = PARAMS["board_width"]["value"]
BT = PARAMS["board_thickness"]["value"]
C = PARAMS["clearance"]["value"]
T = PARAMS["wall"]["value"]
IH = PARAMS["inner_height"]["value"]
SH = PARAMS["standoff_height"]["value"]
SD = PARAMS["standoff_diameter"]["value"]
SHOLE = PARAMS["standoff_hole"]["value"]
USBY = PARAMS["usb_y"]["value"]
USBW = PARAMS["usb_width"]["value"]
PWY = PARAMS["power_y"]["value"]
PWW = PARAMS["power_width"]["value"]
PH = PARAMS["port_height"]["value"]
PM = PARAMS["port_margin"]["value"]

SHOLE = min(SHOLE, SD - 2)
SH = min(SH, IH - BT - PH - 2)
IL = BL + 2 * C
IW = BW + 2 * C
OL = IL + 2 * T
OW = IW + 2 * T
H = T + IH
USBW = min(USBW + 2 * PM, BW - 2)
PWW = min(PWW + 2 * PM, BW - 2)
USBY = min(max(USBY, USBW / 2), BW - USBW / 2)
PWY = min(max(PWY, PWW / 2), BW - PWW / 2)

# Board corner (next to USB) in box coordinates
bx = -IL / 2 + C
by = -IW / 2 + C

# Open box
box = cq.Workplane("XY").box(OL, OW, H, centered=(True, True, False))
box = box.cut(
    cq.Workplane("XY").workplane(offset=T).box(IL, IW, IH + 1, centered=(True, True, False))
)

# Standoffs at the board holes
holes_xy = [(14.0, 2.5), (15.2, 50.8), (66.0, 7.6), (66.0, 35.6)]
pts = [(bx + x, by + y) for x, y in holes_xy]
posts = cq.Workplane("XY").workplane(offset=T / 2).pushPoints(pts).circle(SD / 2).extrude(T / 2 + SH)
box = box.union(posts)
drill = cq.Workplane("XY").workplane(offset=T + 0.5).pushPoints(pts).circle(SHOLE / 2).extrude(SH + 1)
box = box.cut(drill)

# Openings in the -X wall (USB side)
zb = T + SH + BT - 0.5
for yc, w in ((USBY, USBW), (PWY, PWW)):
    cut = cq.Workplane("XY").box(T + 2 * C + 2, w, PH + PM + 0.5, centered=(False, True, False)).translate(
        (-OL / 2 - 1, by + yc, zb)
    )
    box = box.cut(cut)

result = box

EXPECTED_BBOX = (OL, OW, H)
EXPECTED_HOLES = [(SHOLE, 4)]

REFERENCE = (
    cq.Workplane("XY")
    .box(BL, BW, BT, centered=(False, False, False))
    .translate((bx, by, T + SH + 0.01))
)

LOAD_CASE = {
    "description": "Caixa fixada pels forats de la placa; pes de la placa i petits esforços de connexió USB",
    "fixed": [{"type": "side", "side": "-z"}],
    "loads": [{"region": {"type": "point", "center": [-OL / 2, 0, T + SH + BT + PH / 2], "radius": 6}, "force": [-10, 0, 0]}],
}
