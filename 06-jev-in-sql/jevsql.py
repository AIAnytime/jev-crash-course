"""Jev as a set of SQL functions.

DuckDB calls these with a whole column at a time, not row by row, so a query
over a thousand rows turns into a few hundred concurrent API calls instead of a
thousand sequential ones. Results are cached by text, so running the same query
twice only pays once.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pyarrow as pa
from typesafe_sdk import Choice, Noul, Score

import jevlib

MODEL = "jev-latest"
CONCURRENCY = 40

QUESTIONS = {
    "sentiment": Choice(
        instructions="What is the reviewer's overall feeling about the app?",
        criteria={
            "positive": "Broadly happy with it.",
            "neutral": "Mixed or factual, no clear lean.",
            "negative": "Broadly unhappy with it.",
        },
    ),
    "topic": Choice(
        instructions="What is this review mainly about?",
        criteria={
            "performance": "Speed, battery, crashes on load, lag.",
            "ui": "Layout, design, navigation, ease of use.",
            "features": "A capability that exists, is missing, or is wanted.",
            "pricing": "Cost, ads, subscriptions, purchases.",
            "bugs": "Something is broken or behaves incorrectly.",
            "other": "None of the above fits.",
        },
    ),
    "is_bug": Noul(
        instructions=(
            "Does this review report a concrete defect an engineer could act on? "
            "A request for a new feature does not count."
        ),
    ),
    "churn_risk": Score(
        instructions="How likely is this reviewer to stop using the app?",
        criteria=[
            "Committed, recommends it to others",
            "Satisfied, no sign of leaving",
            "Irritated but still using it",
            "Frustrated, looking at alternatives",
            "Has left or says they are leaving",
        ],
    ),
}


class Stats:
    """Counters for one query, read by the progress endpoint while it runs."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.calls = 0
            self.cached = 0
            self.errors = 0
            self.input_tokens = 0
            self.started = time.perf_counter()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "calls": self.calls,
                "cached": self.cached,
                "errors": self.errors,
                "input_tokens": self.input_tokens,
                "cost": jevlib.jev_cost(self.input_tokens),
                "elapsed": time.perf_counter() - self.started,
            }


stats = Stats()
_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _unpack(response) -> dict:
    answers = response.answers
    sentiment = answers["sentiment"]
    topic = answers["topic"]
    churn = answers["churn_risk"]
    return {
        "sentiment": sentiment.choice,
        "sentiment_confidence": sentiment.probabilities.get(sentiment.choice, sentiment.confidence),
        "topic": topic.choice,
        "is_bug": answers["is_bug"].noul,
        "churn_risk": churn.score,
    }


EMPTY = {
    "sentiment": None, "sentiment_confidence": None,
    "topic": None, "is_bug": None, "churn_risk": None,
}


async def _fetch_many(texts: list[str]) -> None:
    """Fill the cache for anything in `texts` that is not already there."""
    missing = []
    with _cache_lock:
        for text in texts:
            if text not in _cache and text not in missing:
                missing.append(text)
    if not missing:
        return

    client = jevlib.async_client(MODEL)
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(text: str) -> None:
        async with semaphore:
            try:
                response = await client.system_one(state={"review": text}, questions=QUESTIONS)
                row = _unpack(response)
                tokens = response.usage.input_tokens
                failed = False
            except Exception:
                row, tokens, failed = dict(EMPTY), 0, True
            with _cache_lock:
                _cache[text] = row
            with stats.lock:
                stats.calls += 1
                stats.input_tokens += tokens
                if failed:
                    stats.errors += 1

    try:
        await asyncio.gather(*(one(t) for t in missing))
    finally:
        await client.aclose()


def _column(texts: list[str], field: str) -> list:
    hits = 0
    with _cache_lock:
        known = {t: _cache.get(t) for t in set(texts)}
    for text, row in known.items():
        if row is not None:
            hits += 1
    with stats.lock:
        stats.cached += hits

    asyncio.run(_fetch_many([t for t in texts if known.get(t) is None]))

    with _cache_lock:
        return [(_cache.get(t) or EMPTY)[field] for t in texts]


def register(connection) -> None:
    """Add the jev_* functions to a DuckDB connection."""
    fields = {
        "jev_sentiment": ("sentiment", "VARCHAR"),
        "jev_sentiment_confidence": ("sentiment_confidence", "DOUBLE"),
        "jev_topic": ("topic", "VARCHAR"),
        "jev_is_bug": ("is_bug", "DOUBLE"),
        "jev_churn_risk": ("churn_risk", "DOUBLE"),
    }
    for name, (field, sql_type) in fields.items():
        def make(field=field):
            def fn(column: pa.Array) -> pa.Array:
                return pa.array(_column(column.to_pylist(), field))
            return fn

        connection.create_function(
            name, make(), ["VARCHAR"], sql_type, type="arrow", side_effects=False
        )


def cache_size() -> int:
    with _cache_lock:
        return len(_cache)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
