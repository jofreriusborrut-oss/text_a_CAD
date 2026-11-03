"""Text a CAD from the terminal.

Examples:
    python cli.py "Placa de 60x80x5 mm amb 4 forats de 6,5 mm..."
    python cli.py --code tests/parts/a_placa.py        (no Claude, run a script)
    python cli.py "..." --out sortida/placa
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

from textacad.config import PROJECT_DIR
from textacad.sandbox import run_code


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower())[:40].strip("_") or "peca"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):          # accents in the Windows console
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Generate a CAD part (STEP + STL) from text.")
    ap.add_argument("description", nargs="?", help="Text description of the part")
    ap.add_argument("--code", type=Path, help="Run this CadQuery file instead of asking Claude")
    ap.add_argument("--out", type=Path, help="Output folder (default: sortida/<name>)")
    args = ap.parse_args()

    if args.code:
        code = args.code.read_text(encoding="utf-8")
        name = args.code.stem
    elif args.description:
        from textacad.generator import generate_code

        print("Demanant el codi a Claude...")
        code = generate_code(args.description)
        name = _slug(args.description)
    else:
        ap.error("Give a description or --code FILE")

    out = args.out or PROJECT_DIR / "sortida" / name
    out.mkdir(parents=True, exist_ok=True)
    (out / "code.py").write_text(code, encoding="utf-8")

    print("Executant el codi CadQuery (procés separat)...")
    res = run_code(code)
    if not res.ok:
        print("\nERROR:\n" + res.error)
        return 1

    shutil.copy(res.step_path, out / f"{name}.step")
    shutil.copy(res.stl_path, out / f"{name}.stl")
    size = " x ".join(f"{v:.1f}" for v in res.info["bbox"]["size"])
    print(f"\nOK  ->  {out}")
    print(f"  Mida total: {size} mm")
    print(f"  Volum:      {res.info['volume_mm3'] / 1000:.2f} cm3")
    print(f"  Sòlid vàlid: {'sí' if res.info['is_valid'] else 'NO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
