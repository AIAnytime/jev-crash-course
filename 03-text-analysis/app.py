"""Video 3 - a text analyser that answers six questions in one round trip.

The interesting measurement is in /api/compare: asking one question and asking
six costs about the same wall clock, because the text is read once and the
questions are answered off that same reading.

    uvicorn app:app --port 8003 --reload
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
    "sentiment": Choice(
        instructions="How does the writer feel about what they are describing?",
        criteria={
            "positive": "Pleased, satisfied, complimentary.",
            "neutral": "Factual or mixed, with no clear lean.",
            "negative": "Unhappy, critical or frustrated.",
        },
    ),
    "intent": Choice(
        instructions="What is the writer trying to do?",
        criteria={
            "question": "Asking for information.",
            "complaint": "Reporting that something is wrong or unfair.",
            "praise": "Saying something worked well.",
            "request": "Asking for something to be done or built.",
            "spam": "Promotional or automated noise.",
        },
    ),
    "language": Choice(
        instructions="What language is the text written in?",
        criteria={
            "english": "English.",
            "japanese": "Japanese.",
            "hindi": "Hindi.",
            "spanish": "Spanish.",
            "other": "Some other language.",
        },
    ),
    "has_personal_info": Noul(
        instructions=(
            "Does the text contain personal information such as a full name, email "
            "address, phone number, address or account number?"
        ),
    ),
    "is_abusive": Noul(
        instructions="Is the text abusive, insulting or hateful towards a person or group?",
    ),
    "formality": Score(
        instructions="How formal is the writing?",
        criteria=[
            "Very casual, slang and shorthand",
            "Everyday conversational",
            "Neutral and businesslike",
            "Formal, careful, written for the record",
        ],
    ),
}

LABELS = {
    "sentiment": "Feeling",
    "intent": "What they want",
    "language": "Language",
    "has_personal_info": "Personal information",
    "is_abusive": "Abusive",
    "formality": "Formality",
}

ONE_QUESTION = {"sentiment": QUESTIONS["sentiment"]}

SAMPLES = [
    "The app crashes every time I open the settings page on my Pixel. Third build in a row.",
    "Thanks for the quick fix yesterday, everything is working again.",
    "Could you add a way to export the report as a spreadsheet?",
    "My account number is 4471-9920 and my email is priya.n@example.com, please check the charge.",
    "このアプリは本当に使いやすいです。ありがとうございます。",
    "WIN A FREE IPHONE NOW!!! CLICK HERE www.definitely-not-a-scam.example",
    "whatever man this is the worst support team i have ever dealt with, totally useless",
    "I am writing to formally request a refund of the duplicate charge applied on 14 March.",
    "does the paid plan include the api or not? cant find it anywhere on the pricing page",
    "La aplicación se cierra sola cuando intento subir una foto.",
    "Battery drain got much worse after the update, phone is hot all day.",
    "Fixed it myself, turned out to be my VPN. Feel free to close the ticket.",
]

app = FastAPI(title="Text analysis")
jev = jevlib.client(MODEL)


class Text(BaseModel):
    text: str


class Lines(BaseModel):
    lines: list[str]


def flatten(answers: dict) -> list[dict]:
    out = []
    for key in QUESTIONS:
        answer = answers.get(key)
        if answer is None:
            continue
        item = {"key": key, "label": LABELS[key]}
        if answer.type == "noul":
            p = answer.noul
            item.update(value="yes" if p >= 0.5 else "no",
                        confidence=max(p, 1 - p),
                        options={"yes": p, "no": 1 - p})
        elif answer.type == "choice":
            item.update(value=answer.choice,
                        confidence=answer.probabilities.get(answer.choice, answer.confidence),
                        options=dict(answer.probabilities))
        else:
            legend = {int(k): v for k, v in (answer.legend or {}).items()}
            probs = {int(k): v for k, v in (answer.probabilities or {}).items()}
            level = max(probs, key=probs.get) if probs else round(answer.score)
            item.update(value=legend.get(level, str(level)),
                        confidence=probs.get(level, answer.confidence),
                        score=answer.score,
                        options={legend.get(k, str(k)): v for k, v in probs.items()})
        out.append(item)
    return out


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES}


@app.post("/api/analyze")
def analyze(body: Text) -> JSONResponse:
    started = time.perf_counter()
    try:
        response = jev.system_one(state={"text": body.text}, questions=QUESTIONS)
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    elapsed = time.perf_counter() - started
    return JSONResponse({
        "seconds": elapsed,
        "input_tokens": response.usage.input_tokens,
        "cost": jevlib.jev_cost(response.usage.input_tokens),
        "answers": flatten(response.answers),
    })


@app.post("/api/compare")
def compare(body: Text) -> JSONResponse:
    """One question against six, on the same text, back to back."""
    out = {}
    for name, questions in (("one", ONE_QUESTION), ("six", QUESTIONS)):
        started = time.perf_counter()
        try:
            response = jev.system_one(state={"text": body.text}, questions=questions)
        except Exception as exc:
            return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
        out[name] = {
            "seconds": time.perf_counter() - started,
            "questions": len(questions),
            "input_tokens": response.usage.input_tokens,
            "cost": jevlib.jev_cost(response.usage.input_tokens),
        }
    return JSONResponse(out)


@app.post("/api/batch")
async def batch(body: Lines) -> JSONResponse:
    lines = [ln.strip() for ln in body.lines if ln.strip()]
    if not lines:
        return JSONResponse({"error": "Nothing to analyse."}, status_code=400)
    client = jevlib.async_client(MODEL)
    semaphore = asyncio.Semaphore(20)

    async def one(text: str) -> dict:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.system_one(state={"text": text}, questions=QUESTIONS)
            except Exception as exc:
                return {"text": text, "error": f"{type(exc).__name__}: {exc}"}
            return {
                "text": text,
                "seconds": time.perf_counter() - started,
                "input_tokens": response.usage.input_tokens,
                "answers": {a["key"]: a for a in flatten(response.answers)},
            }

    started = time.perf_counter()
    rows = await asyncio.gather(*(one(ln) for ln in lines))
    elapsed = time.perf_counter() - started
    await client.aclose()

    ok = [r for r in rows if "error" not in r]
    latencies = sorted(r["seconds"] for r in ok)
    tokens = sum(r["input_tokens"] for r in ok)
    return JSONResponse({
        "rows": rows,
        "seconds": elapsed,
        "per_second": len(ok) / elapsed if elapsed else 0,
        "median_call": latencies[len(latencies) // 2] if latencies else 0,
        "cost": jevlib.jev_cost(tokens),
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
