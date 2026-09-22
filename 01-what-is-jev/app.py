"""Video 1 - what a decision-only model is.

Same message, same three questions, asked twice: once to Jev, once to an LLM.
The point on screen is the clock and the shape of the answer.

    uvicorn app:app --port 8001 --reload
"""

from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Score

import jevlib

MODEL = "jev-latest"
OPENAI_MODEL = "gpt-4o-mini"

# The three question types are the whole API surface, so the demo uses all three.
QUESTIONS = {
    "needs_reply": Noul(
        instructions="Does this message need a reply from a person?",
    ),
    "mood": Choice(
        instructions="What mood is the writer in?",
        criteria={
            "happy": "Pleased, thankful, complimentary.",
            "neutral": "Matter of fact, no strong feeling either way.",
            "upset": "Annoyed, frustrated or angry.",
        },
    ),
    "urgency": Score(
        instructions="How soon does this need attention?",
        criteria=[
            "No rush at all",
            "Some time this week",
            "Today",
            "Right now, someone is blocked",
        ],
    ),
}

PLAIN_LABELS = {
    "needs_reply": "Does this need a reply?",
    "mood": "What mood is the writer in?",
    "urgency": "How soon does it need attention?",
}

EXAMPLES = [
    "Hi - I was charged twice for my subscription this morning and the second "
    "charge is still pending. Can someone look at this today? I need the money back "
    "before rent goes out.",
    "Just wanted to say the new dark mode looks great. No issue, keep it up.",
    "The export button has been greyed out since the update. Not urgent, I can "
    "work around it, but wanted to flag it.",
    "This is the third time I've written in and nobody has answered. I'm cancelling "
    "if I don't hear back.",
]

app = FastAPI(title="What Jev is")
jev = jevlib.client(MODEL)


class Ask(BaseModel):
    text: str


def answer_to_dict(key: str, answer) -> dict:
    """Flatten one Jev answer into something the page can draw."""
    out = {"key": key, "question": PLAIN_LABELS[key], "type": answer.type}
    if answer.type == "noul":
        p = answer.noul
        out.update(
            value="yes" if p >= 0.5 else "no",
            confidence=max(p, 1 - p),
            options={"yes": p, "no": 1 - p},
        )
    elif answer.type == "choice":
        out.update(
            value=answer.choice,
            confidence=answer.probabilities.get(answer.choice, answer.confidence),
            options=dict(answer.probabilities),
        )
    else:
        legend = {int(k): v for k, v in (answer.legend or {}).items()}
        probs = {int(k): v for k, v in (answer.probabilities or {}).items()}
        level = max(probs, key=probs.get) if probs else round(answer.score)
        out.update(
            value=legend.get(level, str(level)),
            confidence=probs.get(level, answer.confidence),
            score=answer.score,
            options={legend.get(k, str(k)): v for k, v in probs.items()},
        )
    return out


@app.get("/api/examples")
def examples() -> dict:
    return {"examples": EXAMPLES}


@app.post("/api/jev")
def ask_jev(body: Ask) -> JSONResponse:
    started = time.perf_counter()
    try:
        response = jev.system_one(state={"message": body.text}, questions=QUESTIONS)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    elapsed = time.perf_counter() - started

    return JSONResponse({
        "model": MODEL,
        "seconds": elapsed,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost": jevlib.jev_cost(response.usage.input_tokens),
        "answers": [answer_to_dict(k, response.answers[k]) for k in QUESTIONS if k in response.answers],
    })


LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "needs_reply": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "enum": ["yes", "no"]},
                "confidence": {"type": "number"},
            },
            "required": ["value", "confidence"],
            "additionalProperties": False,
        },
        "mood": {
            "type": "object",
            "properties": {
                "value": {"type": "string", "enum": ["happy", "neutral", "upset"]},
                "confidence": {"type": "number"},
            },
            "required": ["value", "confidence"],
            "additionalProperties": False,
        },
        "urgency": {
            "type": "object",
            "properties": {
                "value": {
                    "type": "string",
                    "enum": ["No rush at all", "Some time this week", "Today",
                             "Right now, someone is blocked"],
                },
                "confidence": {"type": "number"},
            },
            "required": ["value", "confidence"],
            "additionalProperties": False,
        },
    },
    "required": ["needs_reply", "mood", "urgency"],
    "additionalProperties": False,
}

LLM_PROMPT = (
    "Read the message and answer three questions about it.\n"
    "1. needs_reply: does it need a reply from a person?\n"
    "2. mood: happy, neutral or upset.\n"
    "3. urgency: how soon it needs attention.\n"
    "Confidence is your honest probability that your own answer is right."
)


@app.post("/api/llm")
def ask_llm(body: Ask) -> JSONResponse:
    if not jevlib.has_openai_key():
        return JSONResponse({"error": "No OPENAI_API_KEY in .env."}, status_code=400)
    from openai import OpenAI

    client = OpenAI(api_key=jevlib.openai_key(), timeout=120.0)
    started = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": LLM_PROMPT},
                {"role": "user", "content": body.text},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "triage", "strict": True, "schema": LLM_SCHEMA},
            },
        )
        payload = json.loads(completion.choices[0].message.content)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    elapsed = time.perf_counter() - started

    usage = completion.usage
    answers = [
        {
            "key": key,
            "question": PLAIN_LABELS[key],
            "value": payload[key]["value"],
            "confidence": payload[key]["confidence"],
            "options": None,
        }
        for key in ("needs_reply", "mood", "urgency")
    ]
    # gpt-4o-mini list price, in dollars per 1M tokens.
    cost = usage.prompt_tokens / 1e6 * 0.15 + usage.completion_tokens / 1e6 * 0.60
    return JSONResponse({
        "model": OPENAI_MODEL,
        "seconds": elapsed,
        "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens,
        "cost": cost,
        "answers": answers,
        "raw": json.dumps(payload, indent=2),
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
