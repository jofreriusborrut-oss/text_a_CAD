"""Ask Claude for CadQuery code.

Two interchangeable "backends", chosen with CLAUDE_BACKEND in .env:
- cli: runs `claude -p` (Claude Code, non-interactive). Uses your Claude
       subscription, so there is no per-call API cost.
- api: uses the official `anthropic` Python SDK (pay per use).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .config import Settings, get_settings
from .prompts import SYSTEM_PROMPT, first_request


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

_FENCE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(answer: str) -> str:
    """Keep only the Python code from Claude's answer (drop ``` fences and any text)."""
    blocks = _FENCE.findall(answer)
    if blocks:
        with_params = [b for b in blocks if "PARAMS" in b]
        code = max(with_params or blocks, key=len)
    else:
        code = answer
    code = code.strip()
    if not code:
        raise ClaudeError("Claude returned an empty answer.")
    return code + "\n"


def generate_code(description: str, settings: Settings | None = None) -> str:
    """One request: description -> CadQuery code (not executed yet)."""
    return extract_code(ask_claude(first_request(description), settings))
