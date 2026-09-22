"""GPT baseline -- the same four questions, asked via strict structured output.

The model is asked to self-report a confidence per answer. That self-report is
what the calibration tab holds up against Jev's probabilities.
"""

from __future__ import annotations

import json
import os
import time

from ..config import OPENAI_KEY, has_key
from ..data import to_state
from ..pricing import DEFAULT_OPENAI_MODEL, OPENAI_PRICES, Price
from ..schema import REVIEW_QUESTIONS, QSpec
from .base import Answer, Result, noul_to_answer

SYSTEM = (
    "You label app-store reviews. Answer every question about the review. "
    "Confidence is your honest probability that your own answer is correct, "
    "between 0 and 1 -- not a measure of how strongly the review is worded."
)


def _json_schema(specs: list[QSpec]) -> dict:
    props: dict = {}
    for q in specs:
        if q.kind == "choice":
            props[q.key] = {
                "type": "object",
                "description": q.instructions,
                "properties": {
                    "value": {"type": "string", "enum": list(q.options)},
                    "confidence": {"type": "number"},
                },
                "required": ["value", "confidence"],
                "additionalProperties": False,
            }
        elif q.kind == "noul":
            props[q.key] = {
                "type": "object",
                "description": q.instructions,
                "properties": {"probability": {"type": "number"}},
                "required": ["probability"],
                "additionalProperties": False,
            }
        else:
            props[q.key] = {
                "type": "object",
                "description": q.instructions,
                "properties": {
                    "level": {"type": "integer", "enum": list(range(len(q.levels)))},
                    "confidence": {"type": "number"},
                },
                "required": ["level", "confidence"],
                "additionalProperties": False,
            }
    return {
        "type": "object",
        "properties": props,
        "required": list(props),
        "additionalProperties": False,
    }


def _prompt(specs: list[QSpec], row: dict) -> str:
    lines = [f"REVIEW:\n{json.dumps(to_state(row), indent=2)}", "", "QUESTIONS:"]
    for q in specs:
        lines.append(f"- {q.key}: {q.instructions}")
        if q.kind == "choice":
            for k, v in q.options.items():
                lines.append(f"    {k}: {v}")
        elif q.kind == "noul":
            lines.append("    Answer with probability of yes, 0 to 1.")
        else:
            for i, lv in enumerate(q.levels):
                lines.append(f"    {i}: {lv}")
    return "\n".join(lines)


class GPTProvider:
    name = "gpt"

    def __init__(self, model: str = DEFAULT_OPENAI_MODEL, specs: list[QSpec] | None = None,
                 price: Price | None = None):
        self.model = model
        self.specs = specs or REVIEW_QUESTIONS
        self.price = price or OPENAI_PRICES.get(model, OPENAI_PRICES[DEFAULT_OPENAI_MODEL])
        self._client = None

    @property
    def label(self) -> str:
        return self.model

    @property
    def available(self) -> bool:
        return has_key(OPENAI_KEY)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ[OPENAI_KEY], timeout=120.0)
        return self._client

    async def decide(self, row: dict) -> Result:
        client = self._get_client()
        t0 = time.perf_counter()
        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": _prompt(self.specs, row)},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "review_decisions",
                        "strict": True,
                        "schema": _json_schema(self.specs),
                    },
                },
            )
            payload = json.loads(resp.choices[0].message.content)
        except Exception as exc:
            return Result(
                row_id=row["id"],
                latency_s=time.perf_counter() - t0,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = time.perf_counter() - t0

        answers: dict[str, Answer] = {}
        for q in self.specs:
            got = payload.get(q.key)
            if not isinstance(got, dict):
                continue
            if q.kind == "choice":
                answers[q.key] = Answer(
                    key=q.key, kind="choice", value=got.get("value"),
                    confidence=float(got.get("confidence", 0.0)),
                )
            elif q.kind == "noul":
                answers[q.key] = noul_to_answer(q.key, float(got.get("probability", 0.5)))
            else:
                answers[q.key] = Answer(
                    key=q.key, kind="score", value=int(got.get("level", 0)),
                    confidence=float(got.get("confidence", 0.0)),
                    score=float(got.get("level", 0)),
                )

        u = resp.usage
        return Result(
            row_id=row["id"], answers=answers, latency_s=latency,
            input_tokens=getattr(u, "prompt_tokens", 0) or 0,
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
        )

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return self.price.cost(input_tokens, output_tokens)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
