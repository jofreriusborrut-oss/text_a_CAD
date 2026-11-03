"""Run CadQuery code in a separate Python process with a time limit."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import get_settings

RUNNER = Path(__file__).with_name("runner.py")
STARTUP_LIMIT = 120   # seconds allowed just to load CadQuery (slow on a cold start)


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

    def cleanup(self) -> None:
        """Delete the temporary folder (call it after reading the files)."""
        if self.job_dir and self.job_dir.exists():
            shutil.rmtree(self.job_dir, ignore_errors=True)


def run_code(code: str, timeout: int | None = None, job_dir: Path | None = None) -> RunResult:
    """Execute `code` with runner.py in a child process and collect the results."""
    timeout = timeout or get_settings().exec_timeout
    job_dir = Path(job_dir or tempfile.mkdtemp(prefix="textacad_"))
    job_dir.mkdir(parents=True, exist_ok=True)
    for old in ("part.step", "part.stl", "result.json", "ready", "log.txt"):
        (job_dir / old).unlink(missing_ok=True)
    (job_dir / "code.py").write_text(code, encoding="utf-8")

    ready_file = job_dir / "ready"
    log_path = job_dir / "log.txt"
    with open(log_path, "w", encoding="utf-8") as log:
        proc = subprocess.Popen(
            [sys.executable, str(RUNNER), str(job_dir)],
            cwd=job_dir, stdout=log, stderr=subprocess.STDOUT,
        )
        start = time.monotonic()
        code_start = None
        while proc.poll() is None:
            now = time.monotonic()
            if code_start is None and ready_file.exists():
                code_start = now                     # CadQuery loaded: start the clock
            if code_start is not None and now - code_start > timeout:
                proc.kill()
                proc.wait()
                return RunResult(
                    ok=False,
                    job_dir=job_dir,
                    error=f"TimeoutError: the code took longer than {timeout} s and was stopped. "
                    "Simplify the geometry (fewer operations, no huge loops).",
                )
            if code_start is None and now - start > STARTUP_LIMIT:
                proc.kill()
                proc.wait()
                return RunResult(
                    ok=False,
                    job_dir=job_dir,
                    error=f"CadQuery could not be loaded in {STARTUP_LIMIT} s (is it installed?).",
                )
            time.sleep(0.05)

    result_file = job_dir / "result.json"
    if not result_file.exists():
        # The process died before writing its report (e.g. a crash inside OpenCascade).
        detail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-2000:]
        return RunResult(
            ok=False,
            job_dir=job_dir,
            error=f"The CadQuery process crashed (exit code {proc.returncode}).\n{detail}",
        )

    data = json.loads(result_file.read_text(encoding="utf-8"))
    if not data.get("ok"):
        return RunResult(ok=False, job_dir=job_dir, error=data.get("error"))
    return RunResult(ok=True, job_dir=job_dir, info=data)
