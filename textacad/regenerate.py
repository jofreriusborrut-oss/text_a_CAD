"""Rebuild a part with new PARAMS values, without calling Claude."""
from __future__ import annotations

from .params import ParamsError, apply_values
from .sandbox import run_code


def regenerate(code: str, values: dict[str, float]) -> dict:
    """Return {"ok", "error", "code", "info", "stl", "step"} for the new values."""
    try:
        new_code = apply_values(code, values)
    except ParamsError as exc:
        return {"ok": False, "error": str(exc)}
    run = run_code(new_code)
    try:
        if not run.ok:
            return {"ok": False, "error": run.error}
        return {
            "ok": True,
            "error": None,
            "code": new_code,
            "info": run.info,
            "stl": run.stl_path.read_bytes(),
            "step": run.step_path.read_bytes(),
        }
    finally:
        run.cleanup()
