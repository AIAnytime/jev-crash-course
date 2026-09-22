"""The decision task, defined once.

Both providers are driven from these specs, so the race compares the same four
questions asked the same way -- the only thing that differs is what answers them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class QSpec:
    key: str
    kind: Literal["choice", "noul", "score"]
    instructions: str
    options: dict[str, str] | None = None   # choice only
    levels: list[str] | None = None         # score only


REVIEW_QUESTIONS: list[QSpec] = [
    QSpec(
        key="sentiment",
        kind="choice",
        instructions="What is the reviewer's overall sentiment toward the app?",
        options={
            "positive": "The reviewer is broadly happy with the app.",
            "neutral": "Mixed or factual, with no clear lean either way.",
            "negative": "The reviewer is broadly unhappy with the app.",
        },
    ),
    QSpec(
        key="topic",
        kind="choice",
        instructions="What is the review mainly about?",
        options={
            "performance": "Speed, battery, crashes on load, lag, memory.",
            "ui_ux": "Layout, design, navigation, ease of use.",
            "features": "A capability that exists, is missing, or is requested.",
            "pricing": "Cost, ads, subscriptions, in-app purchases.",
            "bugs": "Something is broken or behaves incorrectly.",
            "other": "None of the above clearly fits.",
        },
    ),
    QSpec(
        key="is_bug",
        kind="noul",
        instructions=(
            "Does this review report a concrete defect that an engineer could "
            "act on? Requests for new features do not count."
        ),
    ),
    QSpec(
        key="churn_risk",
        kind="score",
        instructions="How likely is this reviewer to stop using the app?",
        levels=[
            "Committed user, actively recommends it",
            "Satisfied, no sign of leaving",
            "Irritated but still using it",
            "Actively frustrated, considering alternatives",
            "States they have uninstalled or are leaving",
        ],
    ),
]

QUESTIONS_BY_KEY = {q.key: q for q in REVIEW_QUESTIONS}


def stars_to_sentiment(stars: int) -> str:
    """Ground-truth sentiment label from the review's own star rating."""
    if stars <= 2:
        return "negative"
    if stars == 3:
        return "neutral"
    return "positive"
