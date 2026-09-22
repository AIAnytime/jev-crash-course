"""Shared helpers for the playlist demos: env loading and a Jev client.

Each project folder keeps its own copy so it can be run on its own.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path


def load_env() -> None:
    """Read the nearest .env walking up from this file, without overriding
    anything already set in the environment."""
    here = Path(__file__).resolve()
    for folder in [here.parent, *here.parents]:
        env = folder / ".env"
        if not env.exists():
            continue
        for raw in env.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
        return


def jev_key() -> str:
    load_env()
    for name in ("JEV_API_KEY", "TYPESAFE_API_KEY"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    raise RuntimeError("No Jev key found. Add JEV_API_KEY=... to .env at the repo root.")


def openai_key() -> str:
    load_env()
    value = os.environ.get("OPENAI_API_KEY", "").strip()
    if not value:
        raise RuntimeError("No OPENAI_API_KEY found in .env.")
    return value


def has_openai_key() -> bool:
    try:
        openai_key()
        return True
    except RuntimeError:
        return False


def client(model: str = "jev-latest", timeout: float = 60.0):
    from typesafe_sdk import TypeSafeClient

    return TypeSafeClient(api_key=jev_key(), model=model, timeout=timeout)


def async_client(model: str = "jev-latest", timeout: float = 60.0):
    from typesafe_sdk import AsyncTypeSafeClient

    return AsyncTypeSafeClient(api_key=jev_key(), model=model, timeout=timeout)


@contextmanager
def timed():
    """with timed() as t: ...   then t() is the elapsed seconds."""
    start = time.perf_counter()
    end = None

    def elapsed() -> float:
        return (end if end is not None else time.perf_counter()) - start

    yield elapsed
    end = time.perf_counter()


# Jev's published price: $0.042 per 1M input tokens, output free.
JEV_INPUT_PER_MTOK = 0.042


def jev_cost(input_tokens: int) -> float:
    return input_tokens / 1_000_000 * JEV_INPUT_PER_MTOK
