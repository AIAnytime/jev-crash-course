"""Jev provider -- one system_one call carries all four questions.

That single call is the whole point: the review is encoded once into a shared
KV cache and every question is a parallel branch off it, so four questions cost
roughly what one costs.
"""

from __future__ import annotations

import os
import time

from ..config import TYPESAFE_KEY, has_key
from ..data import to_state
from ..pricing import JEV_PRICE
from ..schema import REVIEW_QUESTIONS, QSpec
from .base import Answer, Result, noul_to_answer


def _build_questions(specs: list[QSpec]) -> dict:
    from typesafe_sdk import Choice, Noul, Score

    out: dict = {}
    for q in specs:
        if q.kind == "choice":
            out[q.key] = Choice(instructions=q.instructions, criteria=q.options)
        elif q.kind == "noul":
            out[q.key] = Noul(instructions=q.instructions)
        else:
            out[q.key] = Score(instructions=q.instructions, criteria=q.levels)
    return out


class JevProvider:
    name = "jev"
    label = "Jev"

    def __init__(self, model: str = "jev-latest", specs: list[QSpec] | None = None):
        self.model = model
        self.specs = specs or REVIEW_QUESTIONS
        self._client = None

    @property
    def available(self) -> bool:
        return has_key(TYPESAFE_KEY)

    def _get_client(self):
        if self._client is None:
            from typesafe_sdk import AsyncTypeSafeClient

            self._client = AsyncTypeSafeClient(
                api_key=os.environ[TYPESAFE_KEY], model=self.model, timeout=60.0
            )
        return self._client

    async def decide(self, row: dict) -> Result:
        client = self._get_client()
        questions = _build_questions(self.specs)
        t0 = time.perf_counter()
        try:
            resp = await client.system_one(state=to_state(row), questions=questions)
        except Exception as exc:  # surfaced per-row rather than killing the run
            return Result(
                row_id=row["id"],
                latency_s=time.perf_counter() - t0,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = time.perf_counter() - t0

        answers: dict[str, Answer] = {}
        for q in self.specs:
            a = resp.answers.get(q.key)
            if a is None:
                continue
            if q.kind == "choice":
                answers[q.key] = Answer(
                    key=q.key,
                    kind="choice",
                    value=a.choice,
                    confidence=a.probabilities.get(a.choice, a.confidence),
                    probabilities=dict(a.probabilities),
                )
            elif q.kind == "noul":
                answers[q.key] = noul_to_answer(q.key, a.noul)
            else:
                probs = {int(k): v for k, v in (a.probabilities or {}).items()}
                level = max(probs, key=probs.get) if probs else round(a.score)
                answers[q.key] = Answer(
                    key=q.key,
                    kind="score",
                    value=level,
                    confidence=probs.get(level, a.confidence),
                    probabilities=probs,
                    score=a.score,
                )

        usage = resp.usage
        return Result(
            row_id=row["id"],
            answers=answers,
            latency_s=latency,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
        )

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return JEV_PRICE.cost(input_tokens, output_tokens)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
