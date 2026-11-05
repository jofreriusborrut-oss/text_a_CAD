"""Text a CAD from the terminal: one description in, CAD files and a technical sheet out.

Examples:
    python cli.py "Plate 60 x 80 x 5 mm with 4 M6 holes 10 mm from the edges"
    python cli.py "Suport en L de 40 x 40 x 30 mm ..." --material asa --simulate --lang ca
    python cli.py --code tests/parts/a_placa.py          (no Claude: run a script you already have)

Each run writes a folder (default sortida/<name>/) with the STEP file for
SolidWorks, STL and 3MF for the slicer, the script and a technical sheet.
For a conversation (ask for changes, sliders, 3D view) use the web
interface instead: python server.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
import types
from pathlib import Path

from textacad import checks, i18n, printability, report
from textacad.config import PROJECT_DIR
from textacad.materials import DEFAULT_MATERIAL, MATERIALS, UseCase, get_material, recommend
from textacad.mesh import MeshError, load_stl
from textacad.params import ParamsError, extract_params
from textacad.protocol import slug
from textacad.sandbox import run_code

ICON = {"ok": "[ok]", "info": "[i] ", "warning": "[!] ", "error": "[X] "}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):            # accents in the Windows console
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Generate a CAD part (STEP + STL + 3MF) from a text description.")
    ap.add_argument("description", nargs="?", help="Text description of the part")
    ap.add_argument("--code", type=Path, help="Run this CadQuery file instead of asking Claude")
    ap.add_argument("--out", type=Path, help="Output folder (default: sortida/<name>)")
    ap.add_argument("--material", default=DEFAULT_MATERIAL, choices=sorted(MATERIALS), help="Material for weight, simulation and sheet")
    ap.add_argument("--simulate", action="store_true", help="Run the stress simulation (script's load case, or a generic one)")
    ap.add_argument("--lang", default="en", choices=i18n.LANGS, help="Language of the checks and the technical sheet")
    args = ap.parse_args()
    material = get_material(args.material)

    note: dict = {}
    if args.code:
        code = args.code.read_text(encoding="utf-8")
        name = slug(args.code.stem)
        request = f"(script {args.code.name})"
        print("Running the CadQuery script in a separate process...")
        run = run_code(code, trusted=True)
        if not run.ok:
            print("\nERROR:\n" + (run.error or ""))
            return 1
    elif args.description:
        from textacad.assistant import design
        from textacad.catalog import find_components
        from textacad.generator import ClaudeError
        from textacad.prompts import first_request

        request = args.description
        components = find_components(request)
        if components:
            print("Real data used for: " + ", ".join(c["name"] for c in components))

        def progress(event: dict) -> None:
            detail = f": {event['detail']}" if event.get("detail") else ""
            print(f"[attempt {event['attempt']}/{event['of']}] {event['stage']}{detail}")

        try:
            outcome = design(first_request(request, components), progress)
        except ClaudeError as exc:
            print(f"\nCould not talk to Claude:\n{exc}")
            return 2
        note = outcome.note.as_dict() if outcome.note else {}
        if outcome.kind == "questions":
            print("\n" + note.get("summary", ""))
            for q in note.get("questions", []):
                print("  ? " + q)
            return 3
        if not outcome.ok:
            print(f"\nNo valid part after {len(outcome.attempts)} attempts. Last problem:\n{outcome.last_error or ''}")
            if outcome.code:
                out = args.out or PROJECT_DIR / "sortida" / "failed"
                out.mkdir(parents=True, exist_ok=True)
                (out / "code_failed.py").write_text(outcome.code, encoding="utf-8")
                print(f"The last script is in {out / 'code_failed.py'}")
            return 1
        code, run = outcome.code, outcome.run
        name = slug(note.get("title") or request)
    else:
        ap.error("Give a description or --code FILE")

    info = run.info
    out = args.out or PROJECT_DIR / "sortida" / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "code.py").write_text(code, encoding="utf-8")
    for file_name, path in run.files().items():
        target = "reference.stl" if file_name.startswith("reference") else f"{name}{Path(file_name).suffix}"
        shutil.copy(path, out / target)
    stl = run.stl_path.read_bytes()
    run.cleanup()

    if note.get("summary"):
        print("\n" + note["summary"])
    for line in note.get("assumptions", []):
        print("  - " + line)
    for line in note.get("questions", []):
        print("  ? " + line)

    print()
    results = checks.run_checks(info, stl, material)
    for c in results:
        title, detail = c.text(args.lang)
        print(f"{ICON[c.level]} {title}" + (f"  ({detail})" if c.level in ("warning", "error") else ""))

    simulation = print_data = None
    try:
        mesh = load_stl(stl)
        print_data = printability.analyse(mesh, material)
        print_data["notes"] = [i18n.pick(i18n.PRINT_NOTES, n, args.lang) for n in print_data["notes"]]
        est = print_data.get("estimate")
        if est:
            print(f"\n3D printing in {material.name}: {print_data['best']['up'].upper()} up, about {est['mass_g']:.0f} g, "
                  f"{est['time_minutes'] // 60} h {est['time_minutes'] % 60:02d} min, {est['material_cost_eur']:.2f} EUR of material")
        if args.simulate:
            from textacad.fea import SimulationError
            from textacad.simulate import LoadCase, default_load_case, run_simulation

            try:
                case = LoadCase.from_dict(info["load_case"]) if info.get("load_case") else default_load_case(mesh)
                result = run_simulation(mesh, case, material, "normal")
                simulation = result.summary()
                print(f"\nSimulation ({case.description or 'generic load'}): highest stress {result.max_stress:.2f} MPa, "
                      f"deflection {result.max_displacement:.3f} mm, safety factor {result.safety_factor:.1f}")
                for w in result.warnings:
                    print("  ! " + i18n.pick(i18n.SIM_WARNINGS, w, args.lang))
                use = UseCase.from_dict({**note.get("use", {}), "stress_mpa": result.max_stress})
                best = [r.material.name for r in recommend(use) if r.suitable][:3]
                if best:
                    print("Suggested materials: " + ", ".join(best))
            except SimulationError as exc:
                print(f"\nSimulation not possible: {exc}")
    except MeshError as exc:
        print(f"\nThe STL could not be analysed: {exc}")

    try:
        params = extract_params(code)
    except (ParamsError, SyntaxError):
        params = {}
    version = types.SimpleNamespace(number=1, created=None, info=info, note=note, params=params,
                                    values={k: v["value"] for k, v in params.items()})
    import time

    version.created = time.time()
    html = report.build(title=note.get("title") or name, version=version, history=[request],
                        checks=[c.as_dict(args.lang) for c in results], material=material,
                        simulation=simulation, print_data=print_data, image=None, lang=args.lang)
    (out / f"{name}-report.html").write_text(html, encoding="utf-8")

    size = " x ".join(f"{v:.1f}" for v in info["bbox"]["size"])
    print(f"\nSaved in {out}")
    print(f"  {name}.step  -> SolidWorks: File > Open, file type STEP")
    print(f"  {name}.stl / {name}.3mf  -> slicer (Cura, PrusaSlicer, Bambu Studio, OrcaSlicer)")
    print(f"  {name}-report.html  -> technical sheet ({size} mm, {info['volume_mm3'] / 1000:.2f} cm3)")
    return 0 if all(c.level != "error" for c in results) else 1


if __name__ == "__main__":
    sys.exit(main())
