"""Ask Claude for CadQuery code.

Two interchangeable "backends", chosen with CLAUDE_BACKEND in .env:
- cli: runs `claude -p` (Claude Code, non-interactive). Uses your Claude
       subscription, so there is no per-call API cost.
- api: uses the official `anthropic` Python SDK (pay per use).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from dataclasses import dataclass, field
from typing import Callable

from .config import Settings, get_settings
from .prompts import SYSTEM_PROMPT, first_request
from .sandbox import RunResult


class ClaudeError(RuntimeError):
    """Claude could not be reached or returned nothing useful."""


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def _find_claude_cli(settings: Settings) -> str:
    if settings.cli_path:
        return settings.cli_path
    # On Windows `claude` is installed as claude.cmd / claude.exe; shutil.which finds both.
    found = shutil.which("claude")
    if not found:
        raise ClaudeError(
            "The `claude` command was not found. Install Claude Code and log in "
            "(run `claude` once in a terminal), or set CLAUDE_CLI_PATH in .env, "
            "or switch to CLAUDE_BACKEND=api."
        )
    return found


def _ask_cli(user_message: str, settings: Settings) -> str:
    exe = _find_claude_cli(settings)
    # Work in an empty temporary folder so Claude Code does not pick up any
    # project files (CLAUDE.md, settings...) from where the app is running.
    with tempfile.TemporaryDirectory(prefix="textacad_claude_") as tmp:
        prompt_file = Path(tmp) / "system_prompt.md"
        prompt_file.write_text(SYSTEM_PROMPT, encoding="utf-8")
        cmd = [
            exe,
            "-p",                                  # print mode: answer once and exit
            "--model", settings.model,
            "--system-prompt-file", str(prompt_file),
            "--tools", "",                         # no tools: we only want text back
            "--output-format", "text",
            "--no-session-persistence",
        ]
        env = dict(os.environ)
        # If an API key is in the environment, Claude Code would bill the API
        # instead of your subscription. Remove it for the CLI backend.
        env.pop("ANTHROPIC_API_KEY", None)
        try:
            proc = subprocess.run(
                cmd,
                input=user_message,               # the message goes through stdin
                capture_output=True,
                text=True,
                encoding="utf-8",
                cwd=tmp,
                env=env,
                timeout=settings.claude_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeError(f"`claude -p` did not answer within {settings.claude_timeout} s.") from exc
        except OSError as exc:
            raise ClaudeError(
                f"Could not start Claude Code ({exe}): {exc}. Check that it is installed and "
                "that CLAUDE_CLI_PATH in .env is right."
            ) from exc
    if proc.returncode != 0:
        raise ClaudeError(
            f"`claude -p` failed (exit code {proc.returncode}):\n"
            f"{(proc.stderr or proc.stdout).strip()[-1500:]}"
        )
    return proc.stdout


def _ask_api(user_message: str, settings: Settings) -> str:
    if not settings.api_key:
        raise ClaudeError("CLAUDE_BACKEND=api but ANTHROPIC_API_KEY is empty in .env.")
    import anthropic

    client = anthropic.Anthropic(api_key=settings.api_key, timeout=settings.claude_timeout)
    try:
        message = client.messages.create(
            model=settings.model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ClaudeError(f"Anthropic API error: {exc}") from exc
    return "".join(block.text for block in message.content if block.type == "text")


def ask_claude(user_message: str, settings: Settings | None = None) -> str:
    """Send one message to Claude and return the raw text answer."""
    settings = settings or get_settings()
    if settings.backend == "cli":
        return _ask_cli(user_message, settings)
    if settings.backend == "api":
        return _ask_api(user_message, settings)
    raise ClaudeError(f"Unknown CLAUDE_BACKEND={settings.backend!r} (use 'cli' or 'api').")


# ---------------------------------------------------------------------------
# Answer -> code
# ---------------------------------------------------------------------------

def extract_code(answer: str) -> str:
    """Keep only the Python code from Claude's answer (drop ``` fences and any text)."""
    from .protocol import extract_code as _extract

    code = _extract(answer)
    if not code:
        raise ClaudeError("Claude returned an empty answer.")
    return code


def generate_code(description: str, settings: Settings | None = None) -> str:
    """One request: description -> CadQuery code (not executed yet)."""
    return extract_code(ask_claude(first_request(description), settings))


# ---------------------------------------------------------------------------
# One-shot generation (used by the terminal interface and the tests).
# The conversational assistant lives in assistant.py.
# ---------------------------------------------------------------------------

MAX_ATTEMPTS = 3


@dataclass
class Attempt:
    number: int
    code: str
    error: str | None = None          # None = this attempt worked


@dataclass
class GenerationResult:
    ok: bool
    description: str
    code: str | None = None
    params: dict | None = None
    run: RunResult | None = None
    attempts: list[Attempt] = field(default_factory=list)
    note: dict = field(default_factory=dict)

    @property
    def last_error(self) -> str | None:
        return self.attempts[-1].error if self.attempts else None


# on_progress(attempt_number, max_attempts, message) lets the caller show where we are.
ProgressFn = Callable[[int, int, str], None]

_STAGE_TEXT = {
    "asking": "Asking Claude for the script...",
    "fixing": "Asking Claude to correct the problem...",
    "running": "Running the CadQuery script...",
    "checking": "Measuring the part...",
    "done": "Done!",
    "done_with_warnings": "Done, with warnings.",
}


def generate_part(
    description: str,
    max_attempts: int = MAX_ATTEMPTS,
    on_progress: ProgressFn | None = None,
    settings: Settings | None = None,
) -> GenerationResult:
    """Ask Claude for code, run it, and send errors back until it works.

    Errors from Claude itself (CLI not installed, no network...) are raised as
    ClaudeError: retrying would not help.
    """
    from .assistant import design
    from .catalog import find_components

    def relay(event: dict) -> None:
        if on_progress:
            text = _STAGE_TEXT.get(event["stage"]) or "Error: " + event.get("detail", "")
            on_progress(event["attempt"], event["of"], text)

    request = first_request(description, find_components(description))
    outcome = design(request, relay, settings, max_attempts)
    result = GenerationResult(ok=outcome.ok, description=description, code=outcome.code,
                              params=outcome.params, run=outcome.run,
                              note=outcome.note.as_dict() if outcome.note else {})
    result.attempts = [Attempt(a.number, a.code or "", a.error) for a in outcome.attempts]
    if outcome.kind == "questions":
        questions = "; ".join(outcome.note.questions) or outcome.note.summary
        result.attempts.append(Attempt(1, "", "Claude needs more information: " + questions))
    return result
