"""Refuse generated scripts that try to do more than build geometry.

The script written by Claude is executed on the user's computer. It only
needs CadQuery and math, so anything else (reading files, the network,
starting programs, poking at Python internals) is rejected BEFORE running
it, and the reason is sent back to Claude like any other error.

This is a guard rail, not a perfect sandbox: the script also runs in a
separate process with a time limit (see sandbox.py).
"""
from __future__ import annotations

import ast

ALLOWED_IMPORTS = {"cadquery", "math"}
FORBIDDEN_CALLS = {
    "open", "exec", "eval", "compile", "__import__", "input", "breakpoint", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "exit", "quit", "show_object", "memoryview",
}
FORBIDDEN_NAMES = {"os", "sys", "subprocess", "shutil", "socket", "pathlib", "importlib", "builtins",
                   "ctypes", "pickle", "requests", "urllib", "http"}


def find_problems(code: str) -> list[str]:
    """Reasons why the script must not be run (empty list = fine).

    Raises SyntaxError if the code is not valid Python.
    """
    tree = ast.parse(code)
    problems: list[str] = []

    def add(node: ast.AST, text: str) -> None:
        problems.append(f"line {getattr(node, 'lineno', '?')}: {text}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in ALLOWED_IMPORTS:
                    add(node, f"`import {alias.name}` is not allowed (only cadquery and math).")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS or node.level:
                add(node, f"`from {node.module} import ...` is not allowed (only cadquery and math).")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_CALLS:
            add(node, f"calling `{node.func.id}()` is not allowed in a part script.")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            add(node, f"using `{node.id}` is not allowed in a part script.")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            add(node, f"accessing `{node.attr}` is not allowed in a part script.")
        elif isinstance(node, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith)):
            add(node, f"`{type(node).__name__.lower()}` statements are not needed in a part script.")
    # One message per distinct problem is enough.
    seen: list[str] = []
    for p in problems:
        if p not in seen:
            seen.append(p)
    return seen[:8]
