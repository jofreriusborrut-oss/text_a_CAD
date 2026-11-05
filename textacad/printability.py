"""3D-printing analysis of a part: best orientation, supports, time and cost.

Everything here is an ESTIMATE meant to compare options before slicing; the
slicer gives the real numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .materials import Material, get_material
from .mesh import Mesh

# Build volumes (X, Y, Z in mm) of common desktop printers.
PRINTERS = {
    "Bambu Lab A1 mini": (180, 180, 180),
    "Creality Ender 3": (220, 220, 250),
    "Prusa MK4": (250, 210, 220),
    "Bambu Lab P1S / X1C": (256, 256, 256),
    "Creality K1 Max": (300, 300, 300),
}

ORIENTATIONS = {
    "+z": (0, 0, 1), "-z": (0, 0, -1),
    "+x": (1, 0, 0), "-x": (-1, 0, 0),
    "+y": (0, 1, 0), "-y": (0, -1, 0),
}

OVERHANG_ANGLE = 45.0         # degrees from vertical that print without support
WALL_THICKNESS = 1.2          # mm of solid shell (3 perimeters with a 0.4 mm nozzle)
INFILL = 0.20                 # fraction of the inside that is filled
FLOW_RATE = 8.0               # mm3/s of plastic, a relaxed average for a 0.4 mm nozzle
TIME_OVERHEAD = 1.35          # travel moves, layer changes, heating


@dataclass
class Orientation:
    up: str                   # which part axis points up, e.g. "+z"
    support_area: float       # mm2 of faces that need support
    bed_area: float           # mm2 touching the bed
    height: float             # mm of print height
    footprint: tuple[float, float]

    def as_dict(self) -> dict:
        return {"up": self.up, "support_area_mm2": round(self.support_area, 1),
                "bed_area_mm2": round(self.bed_area, 1), "height_mm": round(self.height, 2),
                "footprint_mm": [round(self.footprint[0], 1), round(self.footprint[1], 1)]}


def orientations(mesh: Mesh) -> list[Orientation]:
    """The six axis-aligned ways to put the part on the bed, best first.

    Best = least support, then most contact with the bed, then lowest.
    """
    size = mesh.size
    out = []
    for name, up in ORIENTATIONS.items():
        axis = int(np.argmax(np.abs(up)))
        others = [a for a in range(3) if a != axis]
        out.append(Orientation(
            up=name,
            support_area=mesh.overhang_area(up, OVERHANG_ANGLE),
            bed_area=mesh.bed_contact_area(up),
            height=float(size[axis]),
            footprint=(float(size[others[0]]), float(size[others[1]])),
        ))
    total = max(mesh.area, 1e-9)
    out.sort(key=lambda o: (round(o.support_area / total, 3), -round(o.bed_area / total, 3), o.height))
    return out


def fits(footprint: tuple[float, float], height: float, volume: tuple[float, float, float]) -> bool:
    a, b = sorted(footprint)
    x, y = sorted(volume[:2])
    return a <= x and b <= y and height <= volume[2]


def estimate(mesh: Mesh, material: Material | str = "petg") -> dict:
    """Plastic used, time and cost for a typical print (20 % infill, 3 walls)."""
    if isinstance(material, str):
        material = get_material(material)
    volume = mesh.volume
    shell = min(mesh.area * WALL_THICKNESS, volume)
    printed = shell + (volume - shell) * INFILL                 # mm3 of plastic
    grams = printed / 1000 * material.density
    seconds = printed / FLOW_RATE * TIME_OVERHEAD
    return {
        "printed_volume_cm3": round(printed / 1000, 2),
        "solid_fraction": round(printed / volume, 3) if volume > 0 else 1.0,
        "mass_g": round(grams, 1),
        "solid_mass_g": round(volume / 1000 * material.density, 1),
        "time_minutes": int(round(seconds / 60)),
        "material_cost_eur": round(grams / 1000 * material.cost_per_kg, 2),
        "assumptions": {"infill": INFILL, "wall_mm": WALL_THICKNESS, "flow_mm3_s": FLOW_RATE},
    }


def analyse(mesh: Mesh, material: Material | str = "petg") -> dict:
    """Everything the "Print" panel shows."""
    if isinstance(material, str):
        material = get_material(material)
    ranked = orientations(mesh)
    best = ranked[0]
    printers = [{"name": name, "volume_mm": list(vol), "fits": fits(best.footprint, best.height, vol)}
                for name, vol in PRINTERS.items()]
    notes = []
    if best.support_area <= 0.005 * mesh.area:
        notes.append("no_support")
    else:
        notes.append("needs_support")
    if best.bed_area < 0.02 * mesh.area or best.bed_area < 100:
        notes.append("small_bed_contact")
    if best.height > 3 * max(min(best.footprint), 1e-9):
        notes.append("tall_and_thin")
    if material.process == "fdm" and material.z_factor < 0.6:
        notes.append("weak_between_layers")
    if not any(p["fits"] for p in printers):
        notes.append("too_big")
    return {
        "material": {"id": material.id, "name": material.name, "process": material.process,
                     "print_settings": material.print_settings},
        "best": best.as_dict(),
        "orientations": [o.as_dict() for o in ranked],
        "printers": printers,
        "estimate": estimate(mesh, material) if material.process != "cnc" else None,
        "notes": notes,
    }
