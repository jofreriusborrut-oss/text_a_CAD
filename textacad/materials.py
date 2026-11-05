"""Material data and a rule-based material recommender.

The numbers are TYPICAL values from supplier datasheets and handbooks, good
for comparing options and for a first sizing. Printed parts vary a lot with
the printer, the settings and the humidity of the filament: for anything
that matters, check the datasheet of the exact material you buy and test a
printed sample.

Units: E, yield and tensile strength in MPa; density in g/cm3; temperatures
in degrees Celsius; cost in euros per kilogram of raw material.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Material:
    id: str
    name: str
    process: str             # "fdm", "sls" or "cnc"
    E: float                 # Young's modulus (stiffness)
    nu: float                # Poisson's ratio
    yield_strength: float    # stress where permanent deformation starts
    tensile_strength: float
    density: float
    max_service_temp: float  # continuous use without softening (conservative)
    z_factor: float          # strength across the layers / strength along them (1 = isotropic)
    cost_per_kg: float
    ease: int                # 1 (hard to make) .. 5 (easy)
    impact: int              # 1 (brittle) .. 5 (tough)
    uv: int                  # 1 (degrades outdoors) .. 5 (weatherproof)
    chemical: int            # 1 (attacked by fuel/oil) .. 5 (resistant)
    flexible: bool = False
    notes: dict = field(default_factory=dict)      # short note per language: en, ca, es
    print_settings: dict = field(default_factory=dict)

    @property
    def weak_axis_strength(self) -> float:
        """Yield strength to use when the load pulls the layers apart."""
        return self.yield_strength * self.z_factor

    def as_dict(self) -> dict:
        d = asdict(self)
        d["weak_axis_strength"] = round(self.weak_axis_strength, 1)
        return d


def _m(*args, **kw) -> Material:
    return Material(*args, **kw)


MATERIALS: dict[str, Material] = {m.id: m for m in [
    _m("pla", "PLA", "fdm", 3300, 0.36, 55, 60, 1.24, 50, 0.65, 22, 5, 1, 1, 2,
       notes={"en": "Stiff and easy to print, but brittle and soft above 50-55 C. Not for parts near engines, brakes or in a car in summer.",
              "ca": "Rígid i fàcil d'imprimir, però fràgil i tou per sobre de 50-55 C. No serveix a prop de motors o frens, ni dins d'un cotxe a l'estiu.",
              "es": "Rígido y fácil de imprimir, pero frágil y blando por encima de 50-55 C. No sirve cerca de motores o frenos, ni dentro de un coche en verano."},
       print_settings={"nozzle_c": "200-215", "bed_c": "55-60", "enclosure": False}),
    _m("petg", "PETG", "fdm", 2000, 0.38, 45, 50, 1.27, 65, 0.70, 22, 4, 3, 3, 4,
       notes={"en": "Good all-rounder: tougher than PLA, good layer bonding, resists water, oil and most chemicals. Softens around 70 C.",
              "ca": "Bon tot terreny: més tenaç que el PLA, bona unió entre capes, resisteix aigua, oli i la majoria de químics. S'estova cap als 70 C.",
              "es": "Buen todoterreno: más tenaz que el PLA, buena unión entre capas, resiste agua, aceite y la mayoría de químicos. Se ablanda hacia los 70 C."},
       print_settings={"nozzle_c": "230-250", "bed_c": "70-85", "enclosure": False}),
    _m("abs", "ABS", "fdm", 2200, 0.35, 40, 43, 1.05, 85, 0.55, 22, 2, 4, 2, 2,
       notes={"en": "Holds up to about 85 C and takes impacts. Warps without an enclosure, weak between layers, attacked by petrol.",
              "ca": "Aguanta fins a uns 85 C i els cops. Es deforma sense carcassa tancada, és feble entre capes i la benzina l'ataca.",
              "es": "Aguanta hasta unos 85 C y los golpes. Se deforma sin carcasa cerrada, es débil entre capas y la gasolina lo ataca."},
       print_settings={"nozzle_c": "240-260", "bed_c": "95-110", "enclosure": True}),
    _m("asa", "ASA", "fdm", 2100, 0.35, 42, 45, 1.07, 85, 0.55, 24, 3, 4, 5, 3,
       notes={"en": "Like ABS but made for outdoors: keeps colour and strength under sun and rain. Holds up to about 85 C.",
              "ca": "Com l'ABS però pensat per a exterior: manté el color i la resistència al sol i a la pluja. Aguanta fins a uns 85 C.",
              "es": "Como el ABS pero pensado para exterior: mantiene color y resistencia al sol y a la lluvia. Aguanta hasta unos 85 C."},
       print_settings={"nozzle_c": "240-260", "bed_c": "90-110", "enclosure": True}),
    _m("pc", "Polycarbonate (PC)", "fdm", 2300, 0.37, 60, 63, 1.20, 110, 0.60, 40, 2, 5, 3, 2,
       notes={"en": "Very tough and heat resistant (about 110 C). Needs a hot nozzle, a hot bed and an enclosure; absorbs moisture.",
              "ca": "Molt tenaç i resistent a la calor (uns 110 C). Necessita broquet i llit calents i carcassa tancada; absorbeix humitat.",
              "es": "Muy tenaz y resistente al calor (unos 110 C). Necesita boquilla y cama calientes y carcasa cerrada; absorbe humedad."},
       print_settings={"nozzle_c": "260-300", "bed_c": "100-120", "enclosure": True}),
    _m("pa12", "Nylon PA12 (FDM)", "fdm", 1500, 0.39, 45, 48, 1.01, 80, 0.75, 55, 2, 5, 3, 5,
       notes={"en": "Tough, fatigue resistant and unaffected by fuel and oil. The filament must be dried before printing.",
              "ca": "Tenaç, resistent a la fatiga i immune a combustible i oli. Cal assecar el filament abans d'imprimir.",
              "es": "Tenaz, resistente a la fatiga e inmune a combustible y aceite. Hay que secar el filamento antes de imprimir."},
       print_settings={"nozzle_c": "250-270", "bed_c": "80-100", "enclosure": True}),
    _m("pa-cf", "Carbon-fibre nylon (PA-CF)", "fdm", 7000, 0.35, 95, 100, 1.15, 120, 0.45, 80, 2, 3, 4, 5,
       notes={"en": "Very stiff and strong along the layers, holds up to about 120 C. Weak between layers and needs a hardened nozzle.",
              "ca": "Molt rígid i resistent en el pla de les capes, aguanta uns 120 C. Feble entre capes i necessita broquet endurit.",
              "es": "Muy rígido y resistente en el plano de las capas, aguanta unos 120 C. Débil entre capas y necesita boquilla endurecida."},
       print_settings={"nozzle_c": "270-300", "bed_c": "90-110", "enclosure": True, "hardened_nozzle": True}),
    _m("tpu95a", "TPU 95A (flexible)", "fdm", 50, 0.48, 9, 40, 1.21, 70, 0.80, 30, 3, 5, 3, 4, flexible=True,
       notes={"en": "Rubber-like: for bumpers, gaskets and vibration dampers. Not for parts that must keep their shape under load.",
              "ca": "Com una goma: per a topalls, juntes i amortidors de vibració. No per a peces que han de mantenir la forma sota càrrega.",
              "es": "Como una goma: para topes, juntas y amortiguadores de vibración. No para piezas que deben mantener la forma bajo carga."},
       print_settings={"nozzle_c": "220-240", "bed_c": "40-60", "enclosure": False}),
    _m("pa12-sls", "Nylon PA12 (SLS, print service)", "sls", 1650, 0.39, 45, 48, 0.95, 100, 0.90, 60, 4, 4, 3, 5,
       notes={"en": "Ordered from a print service. Almost the same strength in every direction, no supports, good for functional parts.",
              "ca": "Es demana a un servei d'impressió. Quasi la mateixa resistència en totes direccions, sense suports, bo per a peces funcionals.",
              "es": "Se pide a un servicio de impresión. Casi la misma resistencia en todas direcciones, sin soportes, bueno para piezas funcionales."}),
    _m("al6061", "Aluminium 6061-T6", "cnc", 68900, 0.33, 276, 310, 2.70, 150, 1.0, 8, 3, 5, 5, 5,
       notes={"en": "The standard machining alloy: light, strong, easy to mill and to anodise.",
              "ca": "L'aliatge estàndard de mecanitzat: lleuger, resistent, fàcil de fresar i d'anoditzar.",
              "es": "La aleación estándar de mecanizado: ligera, resistente, fácil de fresar y de anodizar."}),
    _m("al7075", "Aluminium 7075-T6", "cnc", 71700, 0.33, 503, 572, 2.81, 120, 1.0, 14, 3, 4, 4, 5,
       notes={"en": "Almost twice as strong as 6061, used in racing and aerospace. More expensive and cannot be welded.",
              "ca": "Quasi el doble de resistent que el 6061, es fa servir en competició i aeronàutica. Més car i no es pot soldar.",
              "es": "Casi el doble de resistente que el 6061, se usa en competición y aeronáutica. Más caro y no se puede soldar."}),
    _m("s235", "Steel S235", "cnc", 210000, 0.30, 235, 360, 7.85, 300, 1.0, 2, 3, 5, 2, 4,
       notes={"en": "Cheap structural steel: very stiff and weldable, but heavy and it rusts unless painted or plated.",
              "ca": "Acer estructural barat: molt rígid i soldable, però pesat i s'oxida si no es pinta o es zinca.",
              "es": "Acero estructural barato: muy rígido y soldable, pero pesado y se oxida si no se pinta o se zinca."}),
    _m("ss304", "Stainless steel 304", "cnc", 193000, 0.29, 215, 505, 8.00, 400, 1.0, 6, 2, 5, 5, 5,
       notes={"en": "Does not rust and handles heat. Heavy and slower to machine than aluminium.",
              "ca": "No s'oxida i aguanta la calor. Pesat i més lent de mecanitzar que l'alumini.",
              "es": "No se oxida y aguanta el calor. Pesado y más lento de mecanizar que el aluminio."}),
    _m("ti64", "Titanium Ti-6Al-4V", "cnc", 113800, 0.34, 880, 950, 4.43, 350, 1.0, 60, 1, 5, 5, 5,
       notes={"en": "Best strength for its weight and corrosion proof. Expensive and hard to machine: only when nothing else works.",
              "ca": "La millor resistència per pes i no es corroeix. Car i difícil de mecanitzar: només quan res més serveix.",
              "es": "La mejor resistencia por peso y no se corroe. Caro y difícil de mecanizar: solo cuando nada más sirve."}),
]}

DEFAULT_MATERIAL = "petg"


def get_material(material_id: str) -> Material:
    try:
        return MATERIALS[material_id.lower()]
    except KeyError:
        raise KeyError(f"Unknown material {material_id!r}. Known: {', '.join(MATERIALS)}") from None


# ---------------------------------------------------------------------------
# Recommendation
# ---------------------------------------------------------------------------

@dataclass
class UseCase:
    """What the part has to survive. Everything is optional."""
    processes: tuple[str, ...] = ("fdm",)   # manufacturing methods the user can use
    max_temp_c: float | None = None         # hottest temperature the part will see
    outdoor: bool = False                   # sun and rain
    fluids: bool = False                    # fuel, oil, brake fluid, solvents
    vibration: bool = False                 # vibration or impacts (vehicles, tools)
    flexible: bool = False                  # the part must bend or damp
    stress_mpa: float | None = None         # highest stress from the simulation, if any

    @classmethod
    def from_dict(cls, data: dict | None) -> "UseCase":
        data = dict(data or {})
        proc = data.get("processes") or data.get("process") or ("fdm",)
        if isinstance(proc, str):
            proc = tuple(p.strip().lower() for p in proc.replace(";", ",").split(",") if p.strip())
        proc = tuple(p for p in proc if p in ("fdm", "sls", "cnc")) or ("fdm",)

        def flag(key: str) -> bool:
            v = data.get(key, False)
            return v.strip().lower() in ("1", "true", "yes", "si", "sí", "y") if isinstance(v, str) else bool(v)

        def number(key: str) -> float | None:
            v = data.get(key)
            if v in (None, "", "null", "none", "unknown"):
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return cls(processes=proc, max_temp_c=number("max_temp_c"), outdoor=flag("outdoor"),
                   fluids=flag("fluids"), vibration=flag("vibration"), flexible=flag("flexible"),
                   stress_mpa=number("stress_mpa"))


def required_safety_factor(material: Material, use: UseCase) -> float:
    """Safety factor to aim for (yield strength / working stress).

    Printed plastics get a higher factor than machined metal because their
    strength varies more from part to part; vibration adds fatigue.
    """
    base = 2.0 if material.process == "cnc" else 3.0
    return base + (1.0 if use.vibration else 0.0)


@dataclass
class Recommendation:
    material: Material
    score: float
    suitable: bool
    reasons: list[str]          # keys of positive points (translated by the interface)
    warnings: list[str]         # keys of problems
    safety_factor: float | None = None
    required_factor: float | None = None

    def as_dict(self) -> dict:
        return {"id": self.material.id, "name": self.material.name, "process": self.material.process,
                "score": round(self.score, 1), "suitable": self.suitable, "reasons": self.reasons,
                "warnings": self.warnings,
                "safety_factor": None if self.safety_factor is None else round(self.safety_factor, 2),
                "required_factor": self.required_factor}


def recommend(use: UseCase, top: int | None = None) -> list[Recommendation]:
    """Rank all materials for a use case, best first. Unsuitable ones come last."""
    out: list[Recommendation] = []
    for m in MATERIALS.values():
        reasons: list[str] = []
        warnings: list[str] = []
        suitable = True
        score = 50.0

        if m.process not in use.processes:
            suitable = False
            warnings.append("process_unavailable")

        if use.flexible != m.flexible:
            suitable = False
            warnings.append("not_flexible" if use.flexible else "too_flexible")

        if use.max_temp_c is not None:
            margin = m.max_service_temp - use.max_temp_c
            if margin < 0:
                suitable = False
                warnings.append("too_hot")
            elif margin < 15:
                score -= 10
                warnings.append("temp_margin_small")
            else:
                score += 5
                reasons.append("temp_ok")

        if use.outdoor:
            score += (m.uv - 3) * 6
            if m.uv <= 1:
                warnings.append("uv_poor")
            elif m.uv >= 4:
                reasons.append("uv_good")
        if use.fluids:
            score += (m.chemical - 3) * 7
            if m.chemical <= 2:
                warnings.append("chemical_poor")
            elif m.chemical >= 4:
                reasons.append("chemical_good")
        if use.vibration:
            score += (m.impact - 3) * 7
            if m.impact <= 1:
                warnings.append("brittle")
            elif m.impact >= 4:
                reasons.append("tough")

        sf = need = None
        if use.stress_mpa and use.stress_mpa > 0:
            need = required_safety_factor(m, use)
            sf = m.weak_axis_strength / use.stress_mpa
            if sf < 1.0:
                suitable = False
                warnings.append("breaks")
            elif sf < need:
                score -= 25 * (1 - sf / need)
                warnings.append("low_safety_factor")
            else:
                score += 8
                reasons.append("strong_enough")

        score += (m.ease - 3) * 5                    # easier to make is better
        score -= min(m.cost_per_kg, 80) / 8          # cheaper is better
        if m.ease >= 4:
            reasons.append("easy")
        if not suitable:
            score -= 1000
        out.append(Recommendation(m, score, suitable, reasons, warnings, sf, need))
    out.sort(key=lambda r: r.score, reverse=True)
    return out[:top] if top else out
