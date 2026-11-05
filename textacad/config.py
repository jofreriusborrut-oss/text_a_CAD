"""Reads settings from the .env file (backend, model, timeouts)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    backend: str          # "cli" or "api"
    model: str
    api_key: str | None
    cli_path: str | None
    exec_timeout: int
    claude_timeout: int
    max_attempts: int = 4
    sessions_dir: Path = PROJECT_DIR / "sortida" / "sessions"


def _int(name: str, default: int, low: int = 1) -> int:
    try:
        return max(low, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def get_settings() -> Settings:
    return Settings(
        backend=os.getenv("CLAUDE_BACKEND", "cli").strip().lower(),
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5").strip(),
        api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        cli_path=os.getenv("CLAUDE_CLI_PATH") or None,
        exec_timeout=_int("EXEC_TIMEOUT", 30),
        claude_timeout=_int("CLAUDE_TIMEOUT", 300),
        max_attempts=_int("MAX_ATTEMPTS", 4),
        sessions_dir=Path(os.getenv("SESSIONS_DIR") or PROJECT_DIR / "sortida" / "sessions"),
    )
