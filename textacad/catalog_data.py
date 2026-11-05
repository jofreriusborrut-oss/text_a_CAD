"""Reference components the assistant can design around.

Each entry gives the dimensions that matter for designing a part that holds,
fits or bolts to that component. When the user's text mentions one of them,
its data is added to the request sent to Claude, so the part is built from
real numbers instead of guesses.

`confidence` tells how far to trust the numbers:
    "standard"   values fixed by an ISO/DIN/NEMA standard
    "datasheet"  taken from the manufacturer's datasheet (source given)
    "typical"    common values that vary between brands: measure your part

All lengths in millimetres. To add your own components without touching this
file, use the "Components" panel of the app (they are saved in
catalog_user.json).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Metric fasteners (ISO)
# ---------------------------------------------------------------------------
# size: (pitch, clearance fine / medium / coarse [ISO 273], tap drill,
#        cap screw head diameter and height [ISO 4762], counterbore diameter [DIN 974-1],
#        countersunk head diameter [ISO 10642], nut across flats and height [ISO 4032],
#        washer outer diameter and thickness [ISO 7089], heat-set insert hole and length)
_METRIC = {
    "M2":   (0.4,  (2.2, 2.4, 2.6),    1.6,  (3.8, 2.0),   4.3,  None,  (4.0, 1.6),   (5.0, 0.3),  (3.2, 4.0)),
    "M2.5": (0.45, (2.7, 2.9, 3.1),    2.05, (4.5, 2.5),   5.0,  None,  (5.0, 2.0),   (6.0, 0.5),  (4.0, 5.7)),
    "M3":   (0.5,  (3.2, 3.4, 3.6),    2.5,  (5.5, 3.0),   6.5,  6.72,  (5.5, 2.4),   (7.0, 0.5),  (4.0, 5.7)),
    "M4":   (0.7,  (4.3, 4.5, 4.8),    3.3,  (7.0, 4.0),   8.0,  8.96,  (7.0, 3.2),   (9.0, 0.8),  (5.6, 8.1)),
    "M5":   (0.8,  (5.3, 5.5, 5.8),    4.2,  (8.5, 5.0),   10.0, 11.2,  (8.0, 4.7),   (10.0, 1.0), (6.4, 9.5)),
    "M6":   (1.0,  (6.4, 6.6, 7.0),    5.0,  (10.0, 6.0),  11.0, 13.44, (10.0, 5.2),  (12.0, 1.6), (8.0, 12.7)),
    "M8":   (1.25, (8.4, 9.0, 10.0),   6.8,  (13.0, 8.0),  15.0, 17.92, (13.0, 6.8),  (16.0, 1.6), (9.6, 12.7)),
    "M10":  (1.5,  (10.5, 11.0, 12.0), 8.5,  (16.0, 10.0), 18.0, 22.4,  (16.0, 8.4),  (20.0, 2.0), None),
    "M12":  (1.75, (13.0, 13.5, 14.5), 10.2, (18.0, 12.0), 20.0, 26.88, (18.0, 10.8), (24.0, 2.5), None),
}


def _fastener(size: str) -> dict:
    pitch, clear, tap, head, cbore, csk, nut, washer, insert = _METRIC[size]
    dims = {
        "thread_pitch": pitch,
        "clearance_hole_fine": clear[0],
        "clearance_hole_medium": clear[1],
        "clearance_hole_coarse": clear[2],
        "tap_drill": tap,
        "cap_screw_head_diameter": head[0],
        "cap_screw_head_height": head[1],
        "counterbore_diameter": cbore,
        "counterbore_depth_flush": round(head[1] + 0.4, 2),
        "hex_nut_across_flats": nut[0],
        "hex_nut_across_corners": round(nut[0] / 0.8660254, 2),
        "hex_nut_height": nut[1],
        "washer_outer_diameter": washer[0],
        "washer_thickness": washer[1],
    }
    if csk:
        dims["countersunk_head_diameter_90deg"] = csk
    if insert:
        dims["heat_set_insert_hole"] = insert[0]
        dims["heat_set_insert_length"] = insert[1]
    low = size.lower()
    return {
        "id": f"metric-{low}",
        "name": f"{size} metric fastener (screw, nut, washer, holes)",
        "category": "fastener",
        "match": [[low]],
        "dims": dims,
        "notes": ("Clearance holes per ISO 273 (use medium unless told otherwise). Cap screw ISO 4762, "
                  "counterbore DIN 974-1, countersunk ISO 10642 (90 degrees), nut ISO 4032, washer ISO 7089. "
                  "For a printed nut trap add 0.2-0.3 mm to the across-flats size. Heat-set insert hole and "
                  "length are typical brass inserts for plastics: check the ones you buy. "
                  "In FDM prints small holes come out about 0.2 mm undersize."),
        "confidence": "standard",
        "source": "ISO 273, ISO 4762, DIN 974-1, ISO 10642, ISO 4032, ISO 7089",
    }


_BEARING_WORDS = ("bearing", "bearings", "rodament", "rodaments", "rodamiento", "rodamientos",
                  "coixinet", "coixinets", "cojinete", "cojinetes", "zz", "2rs")
_PROFILE_WORDS = ("profile", "profiles", "perfil", "perfils", "perfiles", "extrusion", "extrusio",
                  "slot", "vslot")


def _bearing(code: str, d: float, D: float, B: float, extra: str = "") -> dict:
    low = code.lower()
    return {
        "id": f"bearing-{low}",
        "name": f"Ball bearing {code} ({d:g} x {D:g} x {B:g})",
        "category": "bearing",
        "match": [[low, w] for w in _BEARING_WORDS] + [[low + "zz"], [low + "2rs"], [low + "rs"], [low + "z"]],
        "dims": {"bore": d, "outer_diameter": D, "width": B},
        "notes": ("Deep groove ball bearing. For a printed press-fit seat make the pocket 0.05-0.15 mm "
                  "larger than the outer diameter and test with a small ring first; for a machined seat use "
                  "an H7 bore. Leave a shoulder that only touches the outer ring. " + extra).strip(),
        "confidence": "standard",
        "source": "ISO 15 boundary dimensions",
    }


def _aim_eclipse(travel: int) -> dict:
    return {
        "id": f"aim-eclipse-{travel:03d}",
        "name": f"AiM ECLIPSE car/bike linear potentiometer, {travel} mm travel",
        "category": "sensor",
        "match": [["aim", str(travel), w] for w in ("eclipse", "potentiometer", "potenciometre", "potenciometro",
                                                     "sensor", "linear", "lineal")]
                 + [[f"x05elp{travel:03d}"], [f"x05elp{travel:03d}a"], [f"x05elp{travel:03d}apj"],
                    [f"x05elp{travel:03d}abj"], [f"x05elp{travel:03d}fw"]],
        "family": "aim-eclipse",
        "dims": {
            "travel": travel,
            "retracted_mounting_distance": travel + 115,
            "extended_mounting_distance": 2 * travel + 115,
            "body_length": travel + 81,
            "end_thread": "M4x0.7 male, both ends",
            "ball_pin_thread_for_pop_joint": "M4",
        },
        "notes": ("Mounts between two points with M4 ends; sold bare, with ball joints (BJ) or with "
                  "quick-release pop joints (PJ). Keep at least 5 mm of travel spare at each end: bottoming "
                  "out or over-extending destroys the sensor, and it must never take side load or bending. "
                  "Works from -30 to +100 C, IP65, 20-40 g. The datasheet text does not state the body "
                  "diameter: measure it before designing a clamp around the body."),
        "confidence": "datasheet",
        "source": "https://dwls.aim-sportline.com/doc/eng/sensors/eclipse/Datasheet_CarBikeAiM_EclipseLinearPotentiometer_eng.pdf",
    }


COMPONENTS: list[dict] = [
    *[_fastener(s) for s in _METRIC],

    # -- bearings -----------------------------------------------------------
    _bearing("623", 3, 10, 4), _bearing("624", 4, 13, 5), _bearing("625", 5, 16, 5),
    _bearing("626", 6, 19, 6), _bearing("608", 8, 22, 7, "The skateboard bearing."),
    _bearing("688", 8, 16, 5, "Width 5 mm is for the shielded 688ZZ; the open 688 is 4 mm."),
    _bearing("6000", 10, 26, 8), _bearing("6001", 12, 28, 8), _bearing("6002", 15, 32, 9),
    _bearing("6200", 10, 30, 9), _bearing("6201", 12, 32, 10), _bearing("6202", 15, 35, 11),
    _bearing("6203", 17, 40, 12), _bearing("6204", 20, 47, 14), _bearing("6205", 25, 52, 15),
    _bearing("6800", 10, 19, 5), _bearing("6801", 12, 21, 5), _bearing("6802", 15, 24, 5),
    _bearing("6803", 17, 26, 5), _bearing("6804", 20, 32, 7), _bearing("6805", 25, 37, 7),
    {
        "id": "lm8uu", "name": "Linear ball bearing LM8UU (8 x 15 x 24)", "category": "bearing",
        "match": [["lm8uu"]], "dims": {"shaft": 8, "outer_diameter": 15, "length": 24},
        "notes": "For 8 mm smooth rods. Clamp it gently or hold it with zip ties: squeezing deforms it.",
        "confidence": "standard", "source": "ISO 10285 series 1",
    },
    {
        "id": "lm10uu", "name": "Linear ball bearing LM10UU (10 x 19 x 29)", "category": "bearing",
        "match": [["lm10uu"]], "dims": {"shaft": 10, "outer_diameter": 19, "length": 29},
        "notes": "For 10 mm smooth rods.", "confidence": "standard", "source": "ISO 10285 series 1",
    },
    {
        "id": "lm12uu", "name": "Linear ball bearing LM12UU (12 x 21 x 30)", "category": "bearing",
        "match": [["lm12uu"]], "dims": {"shaft": 12, "outer_diameter": 21, "length": 30},
        "notes": "For 12 mm smooth rods.", "confidence": "standard", "source": "ISO 10285 series 1",
    },

    # -- motors -------------------------------------------------------------
    {
        "id": "nema14", "name": "NEMA 14 stepper motor mounting face", "category": "motor",
        "match": [["nema", "14"], ["nema14"]],
        "dims": {"face": 35.2, "bolt_square": 26.0, "bolt": "M3", "pilot_diameter": 22.0, "pilot_height": 2.0,
                 "shaft_diameter": 5.0},
        "notes": "Four M3 threaded holes on a 26 mm square. Make the pilot hole 22.5 mm.",
        "confidence": "standard", "source": "NEMA ICS 16",
    },
    {
        "id": "nema17", "name": "NEMA 17 stepper motor mounting face", "category": "motor",
        "match": [["nema", "17"], ["nema17"]],
        "dims": {"face": 42.3, "bolt_square": 31.0, "bolt": "M3", "bolt_thread_depth": 4.5,
                 "pilot_diameter": 22.0, "pilot_height": 2.0, "shaft_diameter": 5.0},
        "notes": ("Four M3 threaded holes on a 31 mm square, about 4.5 mm deep. Make the pilot hole 22.5 mm "
                  "and the bolt holes 3.4 mm; slots instead of holes allow belt tensioning."),
        "confidence": "standard", "source": "NEMA ICS 16",
    },
    {
        "id": "nema23", "name": "NEMA 23 stepper motor mounting face", "category": "motor",
        "match": [["nema", "23"], ["nema23"]],
        "dims": {"face": 56.4, "bolt_square": 47.14, "bolt_hole_in_motor": 5.0, "pilot_diameter": 38.1,
                 "pilot_height": 1.6, "shaft_diameter": 6.35},
        "notes": "Four 5 mm through holes on a 47.14 mm square (use M4 or M5 bolts). Shaft is 6.35 or 8 mm.",
        "confidence": "standard", "source": "NEMA ICS 16",
    },
    {
        "id": "nema34", "name": "NEMA 34 stepper motor mounting face", "category": "motor",
        "match": [["nema", "34"], ["nema34"]],
        "dims": {"face": 86.0, "bolt_square": 69.6, "bolt_hole_in_motor": 6.5, "pilot_diameter": 73.0,
                 "shaft_diameter": 14.0},
        "notes": "Four 6.5 mm through holes on a 69.6 mm square. Shaft is 12.7 or 14 mm depending on the model.",
        "confidence": "standard", "source": "NEMA ICS 16",
    },
    {
        "id": "servo-sg90", "name": "Micro servo SG90 (9 g)", "category": "motor",
        "match": [["sg90"]],
        "dims": {"body_length": 22.5, "body_width": 12.2, "body_height": 22.7, "tab_span": 32.3,
                 "tab_thickness": 2.5, "tab_bottom_from_base": 15.9, "screw_hole_spacing": 27.8,
                 "screw_hole_diameter": 2.0},
        "notes": "Clones differ by a few tenths: leave 0.3 mm clearance around the body.",
        "confidence": "typical", "source": "Typical SG90 datasheet",
    },
    {
        "id": "servo-mg996r", "name": "Standard servo MG996R", "category": "motor",
        "match": [["mg996r"], ["mg996"]],
        "dims": {"body_length": 40.7, "body_width": 19.7, "body_height": 42.9, "tab_span": 54.0,
                 "screw_hole_spacing_long": 49.5, "screw_hole_spacing_short": 10.0, "screw_hole_diameter": 4.5},
        "notes": "Four mounting holes (49.5 x 10 mm). Leave 0.4 mm clearance around the body.",
        "confidence": "typical", "source": "Typical MG996R datasheet",
    },

    # -- sensors for motorsport data logging --------------------------------
    {
        "id": "aim-eclipse-family", "name": "AiM ECLIPSE car/bike linear potentiometers (all travels)",
        "category": "sensor",
        "match": [["aim", w] for w in ("eclipse", "potentiometer", "potenciometre", "potenciometro", "sensor")],
        "family_of": "aim-eclipse",
        "dims": {"travels": "50, 75, 100, 125, 150, 175, 200, 225, 250",
                 "retracted_mounting_distance": "travel + 115",
                 "body_length": "travel + 81",
                 "end_thread": "M4x0.7 male, both ends"},
        "notes": ("The travel was not given: ask which one, or assume 150 mm for a motorcycle fork and say "
                  "so. Sold bare, with ball joints (BJ) or quick-release pop joints (PJ). Never side-load "
                  "it; keep 5 mm of travel spare at each end. -30 to +100 C, IP65."),
        "confidence": "datasheet",
        "source": "https://dwls.aim-sportline.com/doc/eng/sensors/eclipse/Datasheet_CarBikeAiM_EclipseLinearPotentiometer_eng.pdf",
    },
    *[_aim_eclipse(t) for t in (50, 75, 100, 125, 150, 175, 200)],
    {
        "id": "aim-pot-9.5-075", "name": "AiM car/bike linear potentiometer diameter 9.5, 75 mm travel",
        "category": "sensor",
        "match": [["x05snpj075"], ["aim", "9.5", "75"]],
        "dims": {"travel": 75, "retracted_mounting_distance": 175, "body_length": 157, "body_diameter": 9.5,
                 "ball_pin_diameter": 8.0, "ball_pin_thread": "M4x6"},
        "notes": ("Aluminium body, supplied with pop joints that snap onto two 8 mm ball pins with M4 x 6 "
                  "threads: the bracket only needs an M4 threaded hole or insert for each pin. "
                  "-40 to +150 C, IP67, 26-46 g."),
        "confidence": "datasheet",
        "source": "https://aimsportsystems.com.au/download/doc/eng/sensors/Datasheet_CarBikeLinearPotentiometer9,5_100_eng.pdf",
    },
    {
        "id": "aim-pot-9.5-150", "name": "AiM car/bike linear potentiometer diameter 9.5, 150 mm travel",
        "category": "sensor",
        "match": [["x05snpj150"], ["aim", "9.5", "150"]],
        "dims": {"travel": 150, "retracted_mounting_distance": 260, "body_length": 232, "body_diameter": 9.5,
                 "ball_pin_diameter": 8.0, "ball_pin_thread": "M4x6"},
        "notes": ("Aluminium body, supplied with pop joints that snap onto two 8 mm ball pins with M4 x 6 "
                  "threads. -40 to +150 C, IP67, 26-46 g. The usual choice for a motorcycle front fork."),
        "confidence": "datasheet",
        "source": "https://aimsportsystems.com.au/download/doc/eng/sensors/Datasheet_CarBikeLinearPotentiometer9,5_100_eng.pdf",
    },
    {
        "id": "aim-pot-13", "name": "AiM linear travel sensor, 13 mm body, 5 mm eyelets", "category": "sensor",
        "match": [["aim", "13mm"], ["aim", "13", "eyelet"], ["mc", "206"]],
        "dims": {"body_diameter": 13.0, "eyelet_bore": 5.0,
                 "closed_length_eye_to_eye": "travel + 123 (50 -> 173, 75 -> 198, 100 -> 223, 150 -> 273, 200 -> 323)"},
        "notes": "Older AiM sensor with 5 mm eyelets at both ends (M5 or #10 bolts).",
        "confidence": "datasheet", "source": "https://www.pegasusautoracing.com/productselection.asp?Product=MC-206",
    },
    {
        "id": "pg-sls130", "name": "Penny+Giles SLS130 linear position sensor", "category": "sensor",
        "match": [["sls130"], ["penny", "giles"]],
        "dims": {"body_diameter": 13.0, "rod_end_bore": 5.0, "body_length": "stroke + 85.5",
                 "between_centres_retracted": "stroke + 148.6 (compact version: 25 less)",
                 "strokes": "25, 50, 75, 100, 125, 150, 175, 200"},
        "notes": ("Self-aligning rod-end bearings with 5 mm bore at both ends (M5 bolts), +-12 degrees of "
                  "misalignment. A body clamp kit exists (SA200264). -30 to +100 C. Check the body "
                  "diameter on the datasheet drawing before designing a clamp."),
        "confidence": "datasheet",
        "source": "https://www.cw-industrial.com/getmedia/8b62e6b9-b4f5-49fd-a45f-df80d9414075/SLS130-Technical-Information",
    },
    {
        "id": "guide-fork-travel-sensor", "name": "How a fork travel sensor is mounted on a motorcycle",
        "category": "guide",
        "match": [["sensor", "forquilla"], ["sensor", "horquilla"], ["sensor", "fork"],
                  ["potenciometre", "forquilla"], ["potenciometro", "horquilla"], ["potentiometer", "fork"],
                  ["recorregut", "lineal"], ["recorrido", "lineal"], ["linear", "travel"],
                  ["suspension", "sensor"], ["suspensio", "sensor"], ["motostudent"]],
        "dims": {},
        "notes": ("The sensor body end is fixed to the part of the fork that does not move with the wheel "
                  "(a clamp around the fork tube under the lower triple clamp, or the triple clamp itself) "
                  "and the rod end to the part that moves (the fork foot / axle clamp, often using the "
                  "mudguard or caliper bolts). Design rules: (1) sensor travel must exceed the fork travel "
                  "(120-130 mm forks use a 150 mm sensor) and it must sit about mid-stroke margin at both "
                  "ends; (2) the sensor axis must be parallel to the fork tube, so both brackets need the "
                  "same offset from the tube axis; (3) use ball/pop joints or rod ends: the brackets hold "
                  "an M4 (AiM) or M5 (5 mm rod ends) stud or threaded hole; (4) keep clear of the brake "
                  "caliper, the mudguard, the fairing and the steering lock; (5) a tube clamp needs a slit "
                  "and a pinch bolt (M5 or M6) and 0.2-0.3 mm of clearance on the bore; (6) parts near the "
                  "brake get hot: use ASA, PA-CF or aluminium, not PLA. ALWAYS ask for or state as an "
                  "assumption: the tube diameter where the clamp sits (measure with calipers), the sensor "
                  "model, and the offset of the sensor axis from the tube."),
        "confidence": "typical",
        "source": "Common practice in motorsport data acquisition; see the sensor datasheets",
    },

    # -- electronics --------------------------------------------------------
    {
        "id": "arduino-uno", "name": "Arduino Uno R3 board", "category": "electronics",
        "match": [["arduino", "uno"]],
        "dims": {"board_length": 68.6, "board_width": 53.4, "hole_diameter": 3.2,
                 "holes_xy_from_corner_next_to_usb": "(14.0, 2.5), (15.2, 50.8), (66.0, 7.6), (66.0, 35.6)",
                 "tallest_component": 11.0},
        "notes": ("Hole positions are measured from the board corner next to the USB socket, X along the long "
                  "side. Use M3 screws on standoffs at least 3 mm tall; the USB and power sockets overhang "
                  "the board edge by about 6 mm."),
        "confidence": "standard", "source": "Arduino Uno R3 mechanical drawing",
    },
    {
        "id": "raspberry-pi", "name": "Raspberry Pi 3 / 4 / 5 (model B) board", "category": "electronics",
        "match": [["raspberry", "pi"], ["raspberry"], ["rpi"]],
        "exclude": ["pico"],
        "dims": {"board_length": 85.0, "board_width": 56.0, "hole_diameter": 2.7, "hole_rectangle": "58 x 49",
                 "hole_offset_from_edges": 3.5, "board_thickness": 1.4},
        "notes": "Four M2.5 holes on a 58 x 49 mm rectangle, 3.5 mm from the corner on the GPIO end.",
        "confidence": "standard", "source": "Raspberry Pi mechanical drawings",
    },
    {
        "id": "raspberry-pi-pico", "name": "Raspberry Pi Pico board", "category": "electronics",
        "match": [["raspberry", "pico"], ["pi", "pico"], ["rpi", "pico"]],
        "dims": {"board_length": 51.0, "board_width": 21.0, "hole_diameter": 2.1, "hole_rectangle": "47.0 x 11.4",
                 "board_thickness": 1.0},
        "notes": "Four M2 holes on a 47.0 x 11.4 mm rectangle.",
        "confidence": "standard", "source": "Raspberry Pi Pico datasheet",
    },
    {
        "id": "cell-18650", "name": "18650 Li-ion cell", "category": "electronics",
        "match": [["18650"]], "dims": {"diameter": 18.4, "length": 65.2},
        "notes": "Protected cells are up to 69 mm long and 18.7 mm wide: leave room or ask which type.",
        "confidence": "typical", "source": "IEC 61960 nominal size",
    },
    {
        "id": "cell-21700", "name": "21700 Li-ion cell", "category": "electronics",
        "match": [["21700"]], "dims": {"diameter": 21.2, "length": 70.3},
        "notes": "Leave 0.3 mm of clearance on the diameter.", "confidence": "typical",
        "source": "IEC 61960 nominal size",
    },

    # -- structure and motion -----------------------------------------------
    {
        "id": "profile-2020", "name": "Aluminium extrusion 2020 (20 x 20, slot 6)", "category": "structure",
        "match": [["2020", w] for w in _PROFILE_WORDS],
        "dims": {"side": 20.0, "slot_width": 6.2, "slot_spacing": 20.0, "bolt": "M5", "t_nut": "M5 slot 6"},
        "notes": "Brackets bolt on with M5 screws into T-nuts: use 5.5 mm holes on a 20 mm grid.",
        "confidence": "typical", "source": "Typical B-type 20 series profile",
    },
    {
        "id": "profile-3030", "name": "Aluminium extrusion 3030 (30 x 30, slot 8)", "category": "structure",
        "match": [["3030", w] for w in _PROFILE_WORDS],
        "dims": {"side": 30.0, "slot_width": 8.2, "slot_spacing": 30.0, "bolt": "M6", "t_nut": "M6 slot 8"},
        "notes": "Brackets bolt on with M6 screws into T-nuts: use 6.6 mm holes on a 30 mm grid.",
        "confidence": "typical", "source": "Typical B-type 30 series profile",
    },
    {
        "id": "profile-4040", "name": "Aluminium extrusion 4040 (40 x 40, slot 8)", "category": "structure",
        "match": [["4040", w] for w in _PROFILE_WORDS],
        "dims": {"side": 40.0, "slot_width": 8.2, "slot_spacing": 40.0, "bolt": "M8 or M6", "t_nut": "slot 8"},
        "notes": "Usually M8 (9 mm holes) or M6 screws into slot-8 T-nuts.",
        "confidence": "typical", "source": "Typical B-type 40 series profile",
    },
    {
        "id": "mgn12h", "name": "Linear rail MGN12 with MGN12H carriage", "category": "structure",
        "match": [["mgn12h"], ["mgn12"]],
        "dims": {"carriage_width": 27.0, "carriage_length": 45.4, "carriage_holes": "M3 on 20 x 20",
                 "carriage_thread_depth": 3.5, "rail_width": 12.0, "rail_height": 8.0, "rail_hole_pitch": 25.0,
                 "rail_bolt": "M3", "assembly_height": 13.0},
        "notes": "Carriage top has four M3 threaded holes on a 20 x 20 mm square.",
        "confidence": "typical", "source": "HIWIN MGN series catalogue",
    },
    {
        "id": "mgn9h", "name": "Linear rail MGN9 with MGN9H carriage", "category": "structure",
        "match": [["mgn9h"], ["mgn9"]],
        "dims": {"carriage_width": 20.0, "carriage_length": 39.9, "carriage_holes": "M3 on 15 x 16",
                 "rail_width": 9.0, "rail_height": 6.5, "rail_hole_pitch": 20.0, "rail_bolt": "M3",
                 "assembly_height": 10.0},
        "notes": "Carriage top has four M3 threaded holes, 15 mm apart across the rail and 16 mm along it.",
        "confidence": "typical", "source": "HIWIN MGN series catalogue",
    },
    {
        "id": "t8-nut", "name": "T8 lead screw flange nut", "category": "structure",
        "match": [["t8"]],
        "dims": {"screw_diameter": 8.0, "body_diameter": 10.2, "flange_diameter": 22.0, "flange_thickness": 3.5,
                 "holes": "4 x 3.5 on a 16 mm circle", "total_length": 15.0},
        "notes": "Make the body hole 10.5 mm and use M3 screws on a 16 mm bolt circle.",
        "confidence": "typical", "source": "Typical brass T8 nut",
    },
    {
        "id": "vesa-75", "name": "VESA 75 x 75 monitor mount", "category": "structure",
        "match": [["vesa", "75"]], "dims": {"hole_square": 75.0, "bolt": "M4", "hole_diameter": 4.5},
        "notes": "Four M4 screws on a 75 mm square.", "confidence": "standard", "source": "VESA FDMI MIS-D",
    },
    {
        "id": "vesa-100", "name": "VESA 100 x 100 monitor mount", "category": "structure",
        "match": [["vesa", "100"], ["vesa"]], "exclude": ["75"], "dims": {"hole_square": 100.0, "bolt": "M4", "hole_diameter": 4.5},
        "notes": "Four M4 screws on a 100 mm square.", "confidence": "standard", "source": "VESA FDMI MIS-D",
    },
    {
        "id": "tripod-quarter", "name": "Camera tripod thread 1/4\"-20 UNC", "category": "structure",
        "match": [["tripod"], ["tripode"], ["tripode", "camera"], ["1/4"]],
        "dims": {"thread_major_diameter": 6.35, "clearance_hole": 6.6, "tap_drill": 5.1,
                 "nut_across_flats": 11.1, "nut_height": 5.6},
        "notes": "For a captive nut use an 11.3 mm hexagon pocket. Tripod screws engage about 5 mm.",
        "confidence": "standard", "source": "ISO 1222 / ASME B1.1",
    },
    {
        "id": "handlebar", "name": "Handlebar and tube diameters (bikes and motorcycles)", "category": "structure",
        "match": [["handlebar"], ["handlebars"], ["manillar"], ["semimanillar"], ["semimanillars"], ["clip", "on"]],
        "dims": {"motorcycle_standard": 22.2, "motorcycle_fat_bar_centre": 28.6, "bicycle_road_and_mtb": 31.8,
                 "bicycle_oversize": 35.0, "bicycle_old_standard": 25.4},
        "notes": ("A clamp needs a slit, a pinch bolt and 0.2-0.3 mm of clearance on the bore; a rubber or "
                  "printed shim avoids marking the tube. Always confirm the diameter with calipers."),
        "confidence": "typical", "source": "Common tube standards",
    },
]
