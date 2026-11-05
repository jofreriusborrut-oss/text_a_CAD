"""The design assistant: turns a message from the user into a new version of the part.

    first message  -> Claude writes the script of a new part
    later messages -> Claude changes the current script as asked

After each answer the script is checked, run in the sandbox and MEASURED.
If it fails, or if the measurements do not match what the script itself says
it built (overall size, holes, fit with the mating component), the problem
is sent back to Claude, up to `max_attempts` times in total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import catalog, checks
from .config import Settings, get_settings
from .fea import SimulationError
from .generator import ask_claude
from .params import ParamsError, extract_params
from .prompts import change_request, first_request, fix_request
from .protocol import Answer, AnswerError, Note, parse_answer
from .sandbox import RunResult, run_code
from .session import DesignSession, Version
from .simulate import LoadCase

# on_progress receives {"attempt": n, "of": N, "stage": ..., "detail": ...}
# stage: asking | fixing | running | checking | done | done_with_warnings | error
ProgressFn = Callable[[dict], None]


@dataclass
class Attempt:
    number: int
    code: str | None
    error: str | None = None          # None = this attempt worked


@dataclass
class Outcome:
    kind: str                         # "version", "questions" or "failed"
    note: Note | None = None
    version: Version | None = None
    attempts: list[Attempt] = field(default_factory=list)
    code: str | None = None           # last script (also when it failed)
    params: dict | None = None
    run: RunResult | None = None
    components: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.kind == "version"

    @property
    def last_error(self) -> str | None:
        return self.attempts[-1].error if self.attempts else None


def _clean_load_case(info: dict) -> None:
    """Drop a LOAD_CASE that the simulation could not use (with a note)."""
    if not info.get("load_case"):
        return
    try:
        info["load_case"] = LoadCase.from_dict(info["load_case"]).as_dict()
    except SimulationError as exc:
        info.setdefault("notes", []).append(f"LOAD_CASE ignored: {exc}")
        info["load_case"] = None


def design(request: str, on_progress: ProgressFn | None = None, settings: Settings | None = None,
           max_attempts: int | None = None) -> Outcome:
    """Send `request` to Claude and loop until the script runs and checks out.

    `request` is the complete text for Claude (see prompts.first_request and
    prompts.change_request). Errors from Claude itself (not installed, no
    network...) are raised as generator.ClaudeError: retrying would not help.
    """
    settings = settings or get_settings()
    total = max_attempts or settings.max_attempts
    progress = on_progress or (lambda event: None)
    outcome = Outcome(kind="failed")
    code: str | None = None
    error: str | None = None
    answer: Answer | None = None

    for n in range(1, total + 1):
        last = n == total
        if n == 1:
            progress({"attempt": n, "of": total, "stage": "asking"})
            message = request
        else:
            progress({"attempt": n, "of": total, "stage": "fixing"})
            message = fix_request(request, code or "(no script was returned)", error or "", n, total)

        try:
            answer = parse_answer(ask_claude(message, settings))
        except AnswerError as exc:
            error = str(exc)
            outcome.attempts.append(Attempt(n, None, error))
            progress({"attempt": n, "of": total, "stage": "error", "detail": error})
            continue
        outcome.note = answer.note

        if answer.code is None:
            if n == 1:                       # Claude needs information before building anything
                outcome.kind = "questions"
                return outcome
            error = "The answer contained no ```python block with the script."
            outcome.attempts.append(Attempt(n, None, error))
            progress({"attempt": n, "of": total, "stage": "error", "detail": error})
            continue

        code = answer.code
        attempt = Attempt(n, code)
        outcome.attempts.append(attempt)
        outcome.code = code

        try:
            params = extract_params(code)
        except (ParamsError, SyntaxError) as exc:
            error = f"Problem with the PARAMS dictionary: {exc}"
            attempt.error = error
            progress({"attempt": n, "of": total, "stage": "error", "detail": error})
            continue

        progress({"attempt": n, "of": total, "stage": "running"})
        run = run_code(code, timeout=settings.exec_timeout)
        if run.ok:
            progress({"attempt": n, "of": total, "stage": "checking"})
            error = checks.problems_for_claude(run.info)
        else:
            error = run.error
        attempt.error = error

        # A part that runs but has a quality problem is kept on the last
        # attempt: the checks will show the warning to the user.
        if error is None or (run.ok and last):
            _clean_load_case(run.info)
            outcome.kind, outcome.params, outcome.run = "version", params, run
            progress({"attempt": n, "of": total, "stage": "done" if error is None else "done_with_warnings"})
            return outcome
        progress({"attempt": n, "of": total, "stage": "error",
                  "detail": (error or "").strip().splitlines()[-1][:300]})
        run.cleanup()

    return outcome


def handle_message(session: DesignSession, text: str, on_progress: ProgressFn | None = None,
                   settings: Settings | None = None, base: int | None = None) -> Outcome:
    """Process one message of the user inside a session.

    With no version yet the message describes a new part; otherwise it is a
    change to version `base` (default: the current one). On success a new
    version is added to the session.
    """
    text = text.strip()
    session.add_message("user", text)
    parent: Version | None = None
    if session.versions:
        parent = session.get(base)

    components = catalog.find_components(text)
    if parent is None:
        request = first_request(text, components)
    else:
        request = change_request(text, parent.code, session.history(parent.number),
                                 parent.info, components)

    outcome = design(request, on_progress, settings)
    outcome.components = components
    attempts = [{"number": a.number, "error": a.error} for a in outcome.attempts]

    if outcome.kind == "version":
        run = outcome.run
        try:
            version = session.add_version(
                instruction=text, code=outcome.code, params=outcome.params, info=run.info,
                note=outcome.note.as_dict() if outcome.note else {}, files=run.files(),
                attempts=attempts, components=[c["id"] for c in components],
                parent=parent.number if parent else None,
            )
        finally:
            run.cleanup()
        outcome.version = version
        session.add_message("assistant", kind="design", version=version.number)
    elif outcome.kind == "questions":
        session.add_message("assistant", kind="questions", note=outcome.note.as_dict())
    else:
        session.add_message("assistant", kind="failed", attempts=attempts,
                            error=outcome.last_error or "", code=outcome.code or "")
    session.save()
    return outcome
