"""Video 7 - a first pass over a contract, clause by clause.

Two things happen at once. Every clause is read against the same five questions,
and the contract as a whole is checked for the protections that ought to be in
it. Both are decisions with known answers, which is why this runs in seconds
rather than minutes.

    uvicorn app:app --port 8007 --reload

This is a triage tool. It tells a person which clauses to read first. It does
not give legal advice and it does not replace a lawyer.
"""

from __future__ import annotations

import asyncio
import re
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Score

import jevlib
from data.contracts import SAMPLES

MODEL = "jev-latest"

CLAUSE_QUESTIONS = {
    "kind": Choice(
        instructions="What does this clause deal with?",
        criteria={
            "term_renewal": "How long the agreement lasts and how it renews.",
            "fees": "Price, invoicing, payment timing, price increases.",
            "liability": "Caps on liability, exclusions, indemnities.",
            "service_levels": "Uptime, support, credits, performance promises.",
            "data": "Who owns and may use data, deletion, privacy.",
            "termination": "How either side gets out, notice periods, refunds.",
            "governing_law": "Which law applies and where disputes are heard.",
            "assignment": "Transferring the agreement, change of control.",
            "confidentiality": "Keeping information secret.",
            "other": "Anything else.",
        },
    ),
    "favours": Choice(
        instructions=(
            "Read this clause from the point of view of the party named in "
            "'reviewing_for'. Who does it favour?"
        ),
        criteria={
            "us": "Favours the party we are reviewing for.",
            "balanced": "Even handed, or standard market terms.",
            "them": "Favours the other side.",
        },
    ),
    "risk": Score(
        instructions=(
            "How much of a problem is this clause for the party we are reviewing "
            "for, if it is signed as written?"
        ),
        criteria=[
            "No issue, standard",
            "Minor, worth noting",
            "Worth negotiating",
            "Serious, do not sign as written",
        ],
    ),
    "unusual": Noul(
        instructions=(
            "Is this clause unusual compared with normal commercial terms for an "
            "agreement of this kind?"
        ),
    ),
    "needs_redraft": Noul(
        instructions=(
            "Would this clause have to be changed before the party we are "
            "reviewing for signs it? Standard market terms do not need changing."
        ),
    ),
}

# Things a reasonable agreement should contain. Each is one yes/no over the
# whole document, and the interesting answer is "no".
CHECKLIST = {
    "liability_cap": "Is there a cap on how much each side can owe the other?",
    "mutual_cap": "Is the liability cap the same for both sides?",
    "termination_for_convenience": "Can the party we are reviewing for get out early without proving a breach?",
    "renewal_notice_reasonable": "Is the notice period for stopping renewal 60 days or less?",
    "price_increase_limited": "Is there a limit on how much the price can go up at renewal?",
    "uptime_commitment": "Is there a specific uptime or service level commitment?",
    "data_ownership": "Does the customer clearly keep ownership of its own data?",
    "data_deletion": "Is there a commitment to delete or return data after it ends?",
    "ip_indemnity": "Is the supplier covering intellectual property infringement claims?",
    "assignment_on_sale": "Can the agreement be transferred if the company is sold?",
}

PERSPECTIVES = {
    "customer": "the customer buying the services",
    "supplier": "the supplier providing the services",
}

RISK_WORDS = ["No issue", "Minor", "Negotiate", "Do not sign"]

app = FastAPI(title="Contract review")


class Review(BaseModel):
    text: str
    reviewing_for: str = "customer"


def split_clauses(text: str) -> list[dict]:
    """Numbered clauses if the document has them, paragraphs if it does not."""
    body = text.strip()
    parts = re.split(r"\n(?=\s*\d+\.\s)", body)
    if len(parts) < 3:
        parts = re.split(r"\n\s*\n", body)
    clauses = []
    for part in parts:
        clean = " ".join(part.split())
        if len(clean) < 60:
            continue
        heading = re.match(r"^(\d+\.\s*[A-Z][^.]{0,60}\.)", clean)
        clauses.append({
            "number": len(clauses) + 1,
            "heading": (heading.group(1).strip() if heading else clean[:48] + "…"),
            "text": clean,
        })
    return clauses


def unpack_clause(response) -> dict:
    answers = response.answers
    kind = answers["kind"]
    favours = answers["favours"]
    risk = answers["risk"]
    probs = {int(k): v for k, v in (risk.probabilities or {}).items()}
    level = max(probs, key=probs.get) if probs else round(risk.score)
    return {
        "kind": kind.choice,
        "favours": favours.choice,
        "favours_confidence": favours.probabilities.get(favours.choice, favours.confidence),
        "risk_score": risk.score,
        "risk_level": level,
        "risk_word": RISK_WORDS[min(level, len(RISK_WORDS) - 1)],
        "risk_spread": {RISK_WORDS[int(k)]: v for k, v in probs.items() if int(k) < len(RISK_WORDS)},
        "unusual": answers["unusual"].noul,
        "needs_redraft": answers["needs_redraft"].noul,
        "tokens": response.usage.input_tokens,
    }


@app.get("/api/samples")
def samples() -> dict:
    return {"samples": SAMPLES, "perspectives": PERSPECTIVES}


@app.post("/api/review")
async def review(body: Review) -> JSONResponse:
    clauses = split_clauses(body.text)
    if not clauses:
        return JSONResponse({"error": "No clauses found in that text."}, status_code=400)

    side = PERSPECTIVES.get(body.reviewing_for, PERSPECTIVES["customer"])
    client = jevlib.async_client(MODEL)
    semaphore = asyncio.Semaphore(20)
    started = time.perf_counter()

    async def one_clause(clause: dict) -> dict:
        async with semaphore:
            state = {"reviewing_for": side, "clause": clause["text"]}
            try:
                response = await client.system_one(state=state, questions=CLAUSE_QUESTIONS)
            except Exception as exc:
                return {**clause, "error": f"{type(exc).__name__}: {exc}"}
            return {**clause, **unpack_clause(response)}

    async def whole_document() -> dict:
        state = {"reviewing_for": side, "agreement": body.text}
        questions = {key: Noul(instructions=q) for key, q in CHECKLIST.items()}
        try:
            response = await client.system_one(state=state, questions=questions)
        except Exception as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        return {
            "items": [
                {
                    "key": key,
                    "question": CHECKLIST[key],
                    "probability": response.answers[key].noul,
                    "present": response.answers[key].noul >= 0.5,
                }
                for key in CHECKLIST if key in response.answers
            ],
            "tokens": response.usage.input_tokens,
        }

    clause_results, checklist = await asyncio.gather(
        asyncio.gather(*(one_clause(c) for c in clauses)),
        whole_document(),
    )
    await client.aclose()
    elapsed = time.perf_counter() - started

    ok = [c for c in clause_results if "error" not in c]
    tokens = sum(c.get("tokens", 0) for c in ok) + checklist.get("tokens", 0)
    serious = [c for c in ok if c["risk_level"] >= 2]
    missing = [i for i in checklist.get("items", []) if not i["present"]]

    return JSONResponse({
        "clauses": clause_results,
        "checklist": checklist.get("items", []),
        "summary": {
            "clauses": len(clause_results),
            "to_negotiate": len(serious),
            "missing_protections": len(missing),
            "to_redraft": sum(1 for c in ok if c["needs_redraft"] >= 0.5),
            "worst": max((c["risk_score"] for c in ok), default=0),
        },
        "seconds": elapsed,
        "calls": len(clauses) + 1,
        "cost": jevlib.jev_cost(tokens),
        "reviewing_for": body.reviewing_for,
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
