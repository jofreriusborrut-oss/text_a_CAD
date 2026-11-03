"""Read, validate and modify the PARAMS dictionary of a generated script.

We use Python's `ast` module (the parser Python itself uses) instead of
running the code: this way we can read the parameters safely, and change
their values (for the sliders) without touching the rest of the script.
"""
from __future__ import annotations

import ast
import pprint

REQUIRED_KEYS = ("value", "unit", "min", "max")


class ParamsError(ValueError):
    """The PARAMS dictionary is missing or badly formed."""


def _find_params_node(tree: ast.Module) -> ast.Assign:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PARAMS"
        ):
            return node
    raise ParamsError("No top-level `PARAMS = {...}` dictionary found.")


def extract_params(code: str) -> dict:
    """Return the PARAMS dictionary written in the code (without executing it)."""
    tree = ast.parse(code)
    node = _find_params_node(tree)
    try:
        params = ast.literal_eval(node.value)
    except ValueError as exc:
        raise ParamsError(
            "PARAMS must contain only literal values (numbers and strings), "
            "no variables or calculations."
        ) from exc
    validate_params(params)
    return params


def validate_params(params: object) -> None:
    if not isinstance(params, dict) or not params:
        raise ParamsError("PARAMS must be a non-empty dictionary.")
    for name, spec in params.items():
        if not isinstance(name, str) or not name.isidentifier():
            raise ParamsError(f"Parameter name {name!r} must be a valid identifier.")
        if not isinstance(spec, dict):
            raise ParamsError(f"PARAMS[{name!r}] must be a dictionary.")
        missing = [k for k in REQUIRED_KEYS if k not in spec]
        if missing:
            raise ParamsError(f"PARAMS[{name!r}] is missing the keys {missing}.")
        for k in ("value", "min", "max"):
            if not isinstance(spec[k], (int, float)) or isinstance(spec[k], bool):
                raise ParamsError(f"PARAMS[{name!r}][{k!r}] must be a number.")
        if not spec["min"] <= spec["value"] <= spec["max"]:
            raise ParamsError(
                f"PARAMS[{name!r}]: value {spec['value']} is outside "
                f"[min {spec['min']}, max {spec['max']}]."
            )


def apply_values(code: str, values: dict[str, float]) -> str:
    """Return a copy of `code` where PARAMS[name]["value"] is replaced by `values[name]`.

    Only the PARAMS block is rewritten; the rest of the script stays identical.
    """
    params = extract_params(code)
    for name, value in values.items():
        if name not in params:
            raise ParamsError(f"Unknown parameter {name!r}.")
        spec = params[name]
        if isinstance(spec["value"], int) and float(value).is_integer():
            value = int(value)
        spec["value"] = value

    tree = ast.parse(code)
    node = _find_params_node(tree)
    lines = code.splitlines(keepends=True)
    # Character offsets of the PARAMS statement inside the source.
    start = sum(len(l) for l in lines[: node.lineno - 1]) + node.col_offset
    end = sum(len(l) for l in lines[: node.end_lineno - 1]) + node.end_col_offset
    new_block = "PARAMS = " + pprint.pformat(params, sort_dicts=False, width=100)
    return code[:start] + new_block + code[end:]
