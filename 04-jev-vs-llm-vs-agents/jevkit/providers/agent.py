"""Agent baseline -- the same four questions, but reached through a tool loop.

This is the third lane in the race. It is deliberately an ordinary agent: a
model that can call a tool, decide for itself whether to call it, and only then
answer. Nothing about the task needs a tool. The point of the lane is to show
what the loop costs when the job underneath it is a judgement call.
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
from .gpt import _json_schema, _prompt

SYSTEM = (
    "You triage app-store reviews. Before answering, decide whether you need "
    "background on the app. If you do, call get_app_profile once. Then answer "
    "every question. Confidence is your honest probability that your own answer "
    "is correct."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_app_profile",
            "description": (
                "Background on the app the review is about: category, current "
                "rating, and known open issues."
            ),
            "parameters": {
                "type": "object",
                "properties": {"app": {"type": "string"}},
                "required": ["app"],
                "additionalProperties": False,
            },
        },
    }
]

MAX_STEPS = 4


def _profile(app: str) -> str:
    """Stand-in for whatever internal service an agent would really call."""
    return json.dumps({
        "app": app,
        "category": "utilities",
        "store_rating": 4.1,
        "known_issues": ["slow start on older devices", "occasional upload failures"],
    })


class AgentProvider:
    name = "agent"

    def __init__(self, model: str = DEFAULT_OPENAI_MODEL, specs: list[QSpec] | None = None,
                 price: Price | None = None):
        self.model = model
        self.specs = specs or REVIEW_QUESTIONS
        self.price = price or OPENAI_PRICES.get(model, OPENAI_PRICES[DEFAULT_OPENAI_MODEL])
        self._client = None

    @property
    def label(self) -> str:
        return f"{self.model} agent"

    @property
    def available(self) -> bool:
        return has_key(OPENAI_KEY)

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ[OPENAI_KEY], timeout=180.0)
        return self._client

    async def decide(self, row: dict) -> Result:
        client = self._get_client()
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _prompt(self.specs, row)},
        ]
        input_tokens = output_tokens = 0
        steps = 0
        t0 = time.perf_counter()

        try:
            for _ in range(MAX_STEPS):
                steps += 1
                resp = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=TOOLS,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "review_decisions",
                            "strict": True,
                            "schema": _json_schema(self.specs),
                        },
                    },
                )
                usage = resp.usage
                input_tokens += getattr(usage, "prompt_tokens", 0) or 0
                output_tokens += getattr(usage, "completion_tokens", 0) or 0
                message = resp.choices[0].message

                if message.tool_calls:
                    messages.append(message.model_dump(exclude_none=True))
                    for call in message.tool_calls:
                        args = json.loads(call.function.arguments or "{}")
                        messages.append({
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": _profile(args.get("app", to_state(row)["app"])),
                        })
                    continue

                payload = json.loads(message.content)
                break
            else:
                raise RuntimeError(f"no final answer after {MAX_STEPS} steps")
        except Exception as exc:
            return Result(
                row_id=row["id"],
                latency_s=time.perf_counter() - t0,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=f"{type(exc).__name__}: {exc}",
            )
        latency = time.perf_counter() - t0

        answers: dict[str, Answer] = {}
        for q in self.specs:
            got = payload.get(q.key)
            if not isinstance(got, dict):
                continue
            if q.kind == "choice":
                answers[q.key] = Answer(key=q.key, kind="choice", value=got.get("value"),
                                        confidence=float(got.get("confidence", 0.0)))
            elif q.kind == "noul":
                answers[q.key] = noul_to_answer(q.key, float(got.get("probability", 0.5)))
            else:
                answers[q.key] = Answer(key=q.key, kind="score", value=int(got.get("level", 0)),
                                        confidence=float(got.get("confidence", 0.0)),
                                        score=float(got.get("level", 0)))

        result = Result(row_id=row["id"], answers=answers, latency_s=latency,
                        input_tokens=input_tokens, output_tokens=output_tokens)
        result.steps = steps
        return result

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return self.price.cost(input_tokens, output_tokens)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
