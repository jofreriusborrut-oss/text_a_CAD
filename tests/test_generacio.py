"""REAL tests: the 5 reference descriptions go to Claude and must produce a valid part.

They call Claude (with your subscription via `claude -p`, or the API, depending
on .env), so they are skipped unless you ask for them explicitly.

Windows (PowerShell):   $env:RUN_CLAUDE_TESTS=1; pytest tests/test_generacio.py -v
Windows (cmd):          set RUN_CLAUDE_TESTS=1 && pytest tests/test_generacio.py -v
Linux / macOS:          RUN_CLAUDE_TESTS=1 pytest tests/test_generacio.py -v

Each run saves the generated code and the STEP/STL in sortida/tests/<name>/
so you can open them in SolidWorks.
"""
import os
import shutil

import pytest

from textacad.config import PROJECT_DIR
from textacad.generator import generate_part

from .descripcions import DESCRIPCIONS, MIDES_ESPERADES

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CLAUDE_TESTS") != "1",
    reason="Real Claude calls: set RUN_CLAUDE_TESTS=1 to run them",
)


@pytest.mark.parametrize("name", list(DESCRIPCIONS))
def test_description_gives_valid_part(name):
    gen = generate_part(
        DESCRIPCIONS[name],
        on_progress=lambda n, total, msg: print(f"  [{name}] intent {n}/{total}: {msg}"),
    )
    out = PROJECT_DIR / "sortida" / "tests" / name
    out.mkdir(parents=True, exist_ok=True)
    if gen.code:
        (out / "code.py").write_text(gen.code, encoding="utf-8")
    assert gen.ok, f"No valid part after {len(gen.attempts)} attempts:\n{gen.last_error}"

    shutil.copy(gen.run.step_path, out / f"{name}.step")
    shutil.copy(gen.run.stl_path, out / f"{name}.stl")
    info = gen.run.info
    print(f"  [{name}] {len(gen.attempts)} intent(s), mida {info['bbox']['size']}")

    assert info["is_valid"], "The solid is not valid"
    assert info["n_solids"] == 1
    size = sorted(info["bbox"]["size"])
    expected = MIDES_ESPERADES[name]
    if expected is not None:
        assert size == pytest.approx(sorted(expected), abs=0.5)
    else:
        # Bike mount: the plate is 120 x 60 x 6, the hook makes it deeper.
        assert size[-1] >= 80 and any(abs(s - 60) < 0.5 for s in size)
