"""Video 5 - a small tool that measures writing instead of rewriting it.

Five scores and two yes/no calls, on every keystroke pause. The whole thing is
one dictionary of questions and about a hundred lines of server.

    uvicorn app:app --port 8005 --reload
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Noul, Score

import jevlib

MODEL = "jev-latest"

QUESTIONS = {
    "clarity": Score(
        instructions="How easy is this to understand on one read?",
        criteria=[
            "Confusing, I had to reread it",
            "Takes effort to follow",
            "Mostly clear",
            "Immediately clear",
        ],
    ),
    "warmth": Score(
        instructions="How warm does this sound to the person reading it?",
        criteria=[
            "Cold or hostile",
            "Blunt",
            "Neutral and polite",
            "Genuinely warm",
        ],
    ),
    "hype": Score(
        instructions="How much salesmanship is in the language?",
        criteria=[
            "Plain and factual",
            "Mild enthusiasm",
            "Noticeably promotional",
            "Pure hype",
        ],
    ),
    "concreteness": Score(
        instructions="How specific is this? Does it name real things, numbers and steps?",
        criteria=[
            "Entirely abstract",
            "A few specifics",
            "Mostly specific",
            "Specific throughout, with evidence",
        ],
    ),
    "effort": Score(
        instructions="How much background does a reader need to follow this?",
        criteria=[
            "Anyone can read it",
            "General audience",
            "Needs some domain knowledge",
            "Written for specialists",
        ],
    ),
    "has_ask": Noul(
        instructions="Does the text make it clear what the reader should do next?",
    ),
    "would_reply": Noul(
        instructions="Would a busy person bother to reply to this?",
    ),
}

LABELS = {
    "clarity": "Clarity",
    "warmth": "Warmth",
    "hype": "Hype",
    "concreteness": "Concreteness",
    "effort": "Reader effort",
    "has_ask": "Says what to do next",
    "would_reply": "Worth replying to",
}

SAMPLES = {
    "A cold outreach email": (
        "Hi there,\n\nI wanted to reach out because I believe our revolutionary "
        "platform could unlock tremendous value for your organisation. We work with "
        "industry leaders to drive synergies and accelerate transformation.\n\n"
        "Would you be open to a quick chat?"
    ),
    "The same email, rewritten": (
        "Hi Anna,\n\nYour team posted about the 40 minute build times on the mobile "
        "repo. We cut ours from 38 to 9 minutes last quarter by splitting the test "
        "suite across three runners.\n\nHappy to send the config we used. Want it?"
    ),
    "A bug report": (
        "Upload fails silently for files over 5MB on Chrome 141, macOS. No error in "
        "the UI, 413 in the network tab. Happens on every attempt since Tuesday's "
        "release. Workaround: split the file."
    ),
    "A release note": (
        "We've completely reimagined the dashboard experience with a beautiful new "
        "design that makes everything faster and more delightful than ever before."
    ),
}

app = FastAPI(title="Text measure")
jev = jevlib.client(MODEL)


class Text(BaseModel):
    text: str


class Pair(BaseModel):
    a: str
    b: str


def unpack(answers: dict) -> dict:
    out = {}
    for key in QUESTIONS:
        answer = answers.get(key)
        if answer is None:
            continue
        if answer.type == "noul":
            out[key] = {
                "label": LABELS[key], "kind": "noul",
                "value": "yes" if answer.noul >= 0.5 else "no",
                "probability": answer.noul,
            }
        else:
            legend = {int(k): v for k, v in (answer.legend or {}).items()}
            probs = {int(k): v for k, v in (answer.probabilities or {}).items()}
            level = max(probs, key=probs.get) if probs else round(answer.score)
            out[key] = {
                "label": LABELS[key], "kind": "score",
                "score": answer.score,
                "levels": len(legend) or 4,
                "value": legend.get(level, str(level)),
                "confidence": probs.get(level, answer.confidence),
            }
    return out


async def measure_one(client, text: str) -> dict:
    started = time.perf_counter()
    response = await client.system_one(state={"text": text}, questions=QUESTIONS)
    return {
        "seconds": time.perf_counter() - started,
        "words": len(text.split()),
        "input_tokens": response.usage.input_tokens,
        "cost": jevlib.jev_cost(response.usage.input_tokens),
        "scores": unpack(response.answers),
    }


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES}


@app.post("/api/measure")
def measure(body: Text) -> JSONResponse:
    if not body.text.strip():
        return JSONResponse({"error": "Nothing to measure."}, status_code=400)
    started = time.perf_counter()
    try:
        response = jev.system_one(state={"text": body.text}, questions=QUESTIONS)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    return JSONResponse({
        "seconds": time.perf_counter() - started,
        "words": len(body.text.split()),
        "input_tokens": response.usage.input_tokens,
        "cost": jevlib.jev_cost(response.usage.input_tokens),
        "scores": unpack(response.answers),
    })


@app.post("/api/compare")
async def compare(body: Pair) -> JSONResponse:
    if not body.a.strip() or not body.b.strip():
        return JSONResponse({"error": "Both versions need text."}, status_code=400)
    client = jevlib.async_client(MODEL)
    started = time.perf_counter()
    try:
        left, right = await asyncio.gather(
            measure_one(client, body.a), measure_one(client, body.b)
        )
    except Exception as exc:
        await client.aclose()
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    await client.aclose()
    return JSONResponse({
        "a": left, "b": right,
        "seconds": time.perf_counter() - started,
        "labels": LABELS,
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
