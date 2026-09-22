"""Environment and key detection."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_env() -> Path | None:
    """The nearest .env at or above this project. The playlist keeps one shared
    file at the repo root."""
    for folder in [ROOT, *ROOT.parents]:
        candidate = folder / ".env"
        if candidate.exists():
            return candidate
    return None


def load_env() -> None:
    """Load .env without clobbering anything already exported."""
    env = find_env()
    if env is None:
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))
    resolve_typesafe_key()


def has_key(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


TYPESAFE_KEY = "TYPESAFE_API_KEY"
OPENAI_KEY = "OPENAI_API_KEY"

# The SDK reads TYPESAFE_API_KEY, but the key travels under other names too.
TYPESAFE_ALIASES = ("TYPESAFE_API_KEY", "JEV_API_KEY", "TYPESAFE_KEY")


_found_alias: str | None = None


def resolve_typesafe_key() -> str | None:
    """Accept any of the aliases and normalise onto TYPESAFE_API_KEY.

    Returns the alias the key was originally found under, or None. The original
    name is remembered so the UI can report where the key actually came from
    rather than the name it was copied to."""
    global _found_alias
    if _found_alias:
        return _found_alias
    for name in TYPESAFE_ALIASES:
        value = os.environ.get(name, "").strip()
        if value:
            os.environ[TYPESAFE_KEY] = value
            _found_alias = name
            return name
    return None
