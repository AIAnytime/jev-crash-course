"""Normalised result types shared by every provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class Answer:
    key: str
    kind: str
    value: str | int | None          # chosen label, "yes"/"no", or score level
    confidence: float                # probability mass on `value`, 0..1
    probabilities: dict | None = None
    raw_noul: float | None = None    # P(yes) for noul questions
    score: float | None = None       # continuous position for score questions


@dataclass
class Result:
    row_id: int
    answers: dict[str, Answer] = field(default_factory=dict)
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    steps: int = 1                   # round trips; >1 only for the agent lane
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def noul_to_answer(key: str, p: float) -> Answer:
    """A noul is P(yes). The decision is the side of 0.5 it lands on, and the
    confidence is the mass behind that side."""
    value = "yes" if p >= 0.5 else "no"
    return Answer(
        key=key,
        kind="noul",
        value=value,
        confidence=max(p, 1.0 - p),
        probabilities={"yes": p, "no": 1.0 - p},
        raw_noul=p,
    )


class Provider(Protocol):
    name: str
    label: str

    @property
    def available(self) -> bool: ...

    async def decide(self, row: dict) -> Result: ...

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float: ...

    async def aclose(self) -> None: ...
