"""Loader for the cached review corpus."""

from __future__ import annotations

import json
import random
from functools import lru_cache

from .config import ROOT
from .schema import stars_to_sentiment

REVIEWS_PATH = ROOT / "data" / "reviews.jsonl"


@lru_cache(maxsize=1)
def load_reviews() -> list[dict]:
    if not REVIEWS_PATH.exists():
        raise FileNotFoundError(
            f"{REVIEWS_PATH} is missing. Run scripts/fetch_reviews.py to rebuild it."
        )
    rows = []
    with REVIEWS_PATH.open() as f:
        for line in f:
            row = json.loads(line)
            row["true_sentiment"] = stars_to_sentiment(row["stars"])
            rows.append(row)
    return rows


def sample(n: int, seed: int = 0) -> list[dict]:
    rows = list(load_reviews())
    random.Random(seed).shuffle(rows)
    return rows[:n]


def to_state(row: dict) -> dict:
    """The state both providers see. Star rating is withheld -- it is the label."""
    return {"app": row["app"], "review": row["text"]}
