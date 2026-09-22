"""Video 2 - where this model belongs in an app, and where it does not.

Describe a job your software has to do. Jev decides who should own it: plain
code, Jev itself, or a language model. The built-in list runs all of them at
once so you get the whole picture in one shot.

    uvicorn app:app --port 8002 --reload
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Score

import jevlib

MODEL = "jev-latest"

QUESTIONS = {
    "owner": Choice(
        instructions=(
            "A developer is deciding how to build this job. Who should own it: "
            "ordinary code, a fast decision model, or a language model?"
        ),
        criteria={
            "code": (
                "A fixed rule with a right answer. Arithmetic, lookups, sorting, "
                "date handling, pattern matching. No judgement required."
            ),
            "jev": (
                "A judgement call where the set of possible answers is known in "
                "advance. Classifying, routing, flagging, rating, yes or no."
            ),
            "llm": (
                "The job is to produce new text, or to reason through several "
                "steps. Writing, summarising, translating, explaining, planning."
            ),
        },
    ),
    "fixed_answers": Noul(
        instructions=(
            "Could every acceptable answer to this job be written down as a short "
            "list before you see the input?"
        ),
    ),
    "writes_text": Noul(
        instructions="Does this job require producing new prose for a person to read?",
    ),
    "reasoning": Score(
        instructions="How much step-by-step reasoning does this job need?",
        criteria=[
            "None, it is an instant judgement",
            "A little context has to be weighed",
            "Several facts have to be combined",
            "Genuine multi-step reasoning or planning",
        ],
    ),
}

LABELS = {
    "owner": "Who should own this job?",
    "fixed_answers": "Are the possible answers known in advance?",
    "writes_text": "Does it have to write prose?",
    "reasoning": "How much reasoning does it need?",
}

OWNER_TEXT = {
    "code": "Plain code",
    "jev": "Jev",
    "llm": "A language model",
}

# A spread of jobs from a normal product. Some obviously belong to code, some to
# a language model, and the interesting ones sit in between.
TASKS = [
    "Decide whether a support ticket is about billing, a bug, or a feature request",
    "Write the reply that gets sent back to the customer",
    "Work out how many days are left until a subscription renews",
    "Flag a product review as containing personal information",
    "Summarise a 40 page contract into one page for the legal team",
    "Rate how angry a customer message sounds, on a scale",
    "Decide if an uploaded photo filename looks like a receipt",
    "Sort search results by price, low to high",
    "Decide whether a comment breaks the community rules",
    "Draft three subject lines for a marketing email",
    "Decide which of six teams a new ticket should be routed to",
    "Check that an email address is formatted correctly",
]


app = FastAPI(title="Where to use Jev")
jev = jevlib.client(MODEL)


class Job(BaseModel):
    text: str


def pack(response) -> dict:
    answers = response.answers
    owner = answers["owner"]
    reasoning = answers["reasoning"]
    legend = {int(k): v for k, v in (reasoning.legend or {}).items()}
    probs = {int(k): v for k, v in (reasoning.probabilities or {}).items()}
    level = max(probs, key=probs.get) if probs else round(reasoning.score)
    return {
        "owner": owner.choice,
        "owner_text": OWNER_TEXT.get(owner.choice, owner.choice),
        "owner_spread": {OWNER_TEXT.get(k, k): v for k, v in owner.probabilities.items()},
        "owner_confidence": owner.probabilities.get(owner.choice, owner.confidence),
        "fixed_answers": answers["fixed_answers"].noul,
        "writes_text": answers["writes_text"].noul,
        "reasoning_score": reasoning.score,
        "reasoning_text": legend.get(level, str(level)),
        "input_tokens": response.usage.input_tokens,
    }


@app.get("/api/tasks")
def tasks() -> dict:
    return {"tasks": TASKS, "labels": LABELS}


@app.post("/api/decide")
def decide(job: Job) -> JSONResponse:
    started = time.perf_counter()
    try:
        response = jev.system_one(state={"job": job.text}, questions=QUESTIONS)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    out = pack(response)
    out["seconds"] = time.perf_counter() - started
    out["cost"] = jevlib.jev_cost(out["input_tokens"])
    out["job"] = job.text
    return JSONResponse(out)


@app.post("/api/batch")
async def batch() -> JSONResponse:
    """Every built-in job at once. One question set, twelve parallel calls."""
    client = jevlib.async_client(MODEL)
    started = time.perf_counter()

    async def one(text: str) -> dict:
        try:
            response = await client.system_one(state={"job": text}, questions=QUESTIONS)
        except Exception as exc:
            return {"job": text, "error": f"{type(exc).__name__}: {exc}"}
        out = pack(response)
        out["job"] = text
        return out

    rows = await asyncio.gather(*(one(t) for t in TASKS))
    await client.aclose()
    tokens = sum(r.get("input_tokens", 0) for r in rows)
    return JSONResponse({
        "rows": rows,
        "seconds": time.perf_counter() - started,
        "cost": jevlib.jev_cost(tokens),
        "input_tokens": tokens,
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
