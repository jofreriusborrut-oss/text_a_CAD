"""Run CadQuery code in a separate Python process with a time limit."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import get_settings

RUNNER = Path(__file__).with_name("runner.py")


@dataclass
class RunResult:
    ok: bool
    error: str | None = None
    job_dir: Path | None = None
    info: dict = field(default_factory=dict)   # measurements returned by runner.py

    @property
    def step_path(self) -> Path:
        return self.job_dir / "part.step"

    @property
    def stl_path(self) -> Path:
        return self.job_dir / "part.stl"


def run_code(code: str, timeout: int | None = None, job_dir: Path | None = None) -> RunResult:
    """Execute `code` with runner.py in a child process and collect the results."""
    timeout = timeout or get_settings().exec_timeout
    job_dir = Path(job_dir or tempfile.mkdtemp(prefix="textacad_"))
    job_dir.mkdir(parents=True, exist_ok=True)
    for old in ("part.step", "part.stl", "result.json"):
        (job_dir / old).unlink(missing_ok=True)
    (job_dir / "code.py").write_text(code, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(RUNNER), str(job_dir)],
            cwd=job_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(
            ok=False,
            job_dir=job_dir,
            error=f"TimeoutError: the code took longer than {timeout} s and was stopped. "
            "Simplify the geometry (fewer operations, no huge loops).",
        )

    result_file = job_dir / "result.json"
    if not result_file.exists():
        # The process died before writing its report (e.g. a crash inside OpenCascade).
        detail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        return RunResult(
            ok=False,
            job_dir=job_dir,
            error=f"The CadQuery process crashed (exit code {proc.returncode}).\n{detail}",
        )

    data = json.loads(result_file.read_text(encoding="utf-8"))
    if not data.get("ok"):
        return RunResult(ok=False, job_dir=job_dir, error=data.get("error"))
    return RunResult(ok=True, job_dir=job_dir, info=data)
