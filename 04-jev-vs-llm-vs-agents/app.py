"""Video 4 - three lanes over the same reviews: decision model, language model, agent.

    uvicorn app:app --port 8004 --reload

The race streams over server-sent events so the page fills as rows land. The
engine underneath is jevkit/, which is also what the older Streamlit front end
in streamlit_app.py uses.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from jevkit import data
from jevkit.config import OPENAI_KEY, load_env, resolve_typesafe_key
from jevkit.metrics import accuracy, brier, ece, reliability
from jevkit.pricing import DEFAULT_OPENAI_MODEL, OPENAI_PRICES
from jevkit.providers.agent import AgentProvider
from jevkit.providers.gpt import GPTProvider
from jevkit.providers.jev import JevProvider
from jevkit.runner import race
from jevkit.schema import REVIEW_QUESTIONS

load_env()

app = FastAPI(title="Jev vs LLM vs agent")

LANES = {
    "jev": lambda model: JevProvider(),
    "gpt": lambda model: GPTProvider(model=model),
    "agent": lambda model: AgentProvider(model=model),
}


def build(lanes: list[str], model: str):
    return [LANES[name](model) for name in lanes if name in LANES]


@app.get("/api/config")
def config() -> dict:
    return {
        "jev_key": bool(resolve_typesafe_key()),
        "openai_key": bool(os.environ.get(OPENAI_KEY, "").strip()),
        "models": list(OPENAI_PRICES),
        "default_model": DEFAULT_OPENAI_MODEL,
        "rows_available": len(data.load_reviews()),
        "questions": [
            {"key": q.key, "kind": q.kind, "instructions": q.instructions}
            for q in REVIEW_QUESTIONS
        ],
    }


def snapshot(tallies, providers, elapsed: float) -> dict:
    by_name = {p.name: p for p in providers}
    lanes = []
    for name, tally in tallies.items():
        provider = by_name[name]
        lanes.append({
            "name": name,
            "label": tally.label,
            "done": tally.done,
            "errors": tally.errors,
            "wall_s": tally.wall_s,
            "p50_latency": tally.p50_latency,
            "rows_per_s": tally.rows_per_s,
            "input_tokens": tally.input_tokens,
            "output_tokens": tally.output_tokens,
            "cost": provider.cost_usd(tally.input_tokens, tally.output_tokens),
            "finished": tally.finished,
            "steps": sum(getattr(r, "steps", 1) for r in tally.results),
        })
    return {"elapsed": elapsed, "lanes": lanes}


def score_calibration(tallies, rows_by_id) -> dict:
    """Sentiment against the reviewer's own star rating, which nobody was shown."""
    out = {}
    for name, tally in tallies.items():
        pairs = []
        for result in tally.results:
            if not result.ok:
                continue
            answer = result.answers.get("sentiment")
            if answer is None or answer.value is None:
                continue
            truth = rows_by_id[result.row_id]["true_sentiment"]
            pairs.append((float(answer.confidence), answer.value == truth))
        if not pairs:
            continue
        out[name] = {
            "label": tally.label,
            "n": len(pairs),
            "accuracy": accuracy(pairs),
            "ece": ece(pairs),
            "brier": brier(pairs),
            "bins": [
                {"lo": b.lo, "hi": b.hi, "n": b.n,
                 "confidence": b.mean_confidence, "accuracy": b.accuracy}
                for b in reliability(pairs)
            ],
        }
    return out


@app.get("/api/race")
async def race_stream(n: int = 100, concurrency: int = 20, lanes: str = "jev,gpt",
                      model: str = DEFAULT_OPENAI_MODEL, seed: int = 0):
    wanted = [name for name in lanes.split(",") if name.strip()]
    providers = [p for p in build(wanted, model) if p.available]
    rows = data.sample(min(n, len(data.load_reviews())), seed=seed)
    rows_by_id = {r["id"]: r for r in rows}

    async def events():
        if not providers:
            yield f"data: {json.dumps({'error': 'No lane has an API key.'})}\n\n"
            return

        queue: asyncio.Queue = asyncio.Queue()

        def on_event(tallies, elapsed):
            queue.put_nowait(snapshot(tallies, providers, elapsed))

        task = asyncio.create_task(race(providers, rows, concurrency, on_event))
        yield f"data: {json.dumps({'start': True, 'rows': len(rows), 'lanes': [p.name for p in providers]})}\n\n"

        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=0.4)
                yield f"data: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                if task.done() and queue.empty():
                    break
            if task.done() and queue.empty():
                break

        try:
            tallies = await task
        except Exception as exc:
            yield f"data: {json.dumps({'error': f'{type(exc).__name__}: {exc}'})}\n\n"
            return

        final = snapshot(tallies, providers, max(t.wall_s for t in tallies.values()))
        final["done"] = True
        final["calibration"] = score_calibration(tallies, rows_by_id)
        final["samples"] = [
            {
                "review": rows_by_id[r.row_id]["text"][:150],
                "stars": rows_by_id[r.row_id]["stars"],
                "by_lane": {
                    name: {
                        key: {"value": str(a.value), "confidence": a.confidence}
                        for key, a in next(
                            (res.answers for res in t.results if res.row_id == r.row_id and res.ok),
                            {},
                        ).items()
                    }
                    for name, t in tallies.items()
                },
            }
            for r in list(tallies.values())[0].results[:8] if r.ok
        ]
        yield f"data: {json.dumps(final)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class Ticket(BaseModel):
    text: str


PROPOSE_SYSTEM = (
    "You triage inbound messages for a mobile app team. Propose 3 to 5 distinct, "
    "concrete actions that could reasonably be taken. Do not choose between them. "
    'Return JSON: {"actions":[{"id":"snake_case","description":"one line"}]}'
)


@app.post("/api/pattern")
async def pattern(body: Ticket) -> JSONResponse:
    """The shape worth copying: the language model proposes, Jev picks, code acts."""
    if not os.environ.get(OPENAI_KEY, "").strip():
        return JSONResponse({"error": "No OPENAI_API_KEY in .env."}, status_code=400)
    from openai import AsyncOpenAI
    from typesafe_sdk import AsyncTypeSafeClient, Choice, Score

    openai_client = AsyncOpenAI(api_key=os.environ[OPENAI_KEY], timeout=120.0)
    t0 = time.perf_counter()
    try:
        completion = await openai_client.chat.completions.create(
            model=DEFAULT_OPENAI_MODEL,
            messages=[
                {"role": "system", "content": PROPOSE_SYSTEM},
                {"role": "user", "content": body.text},
            ],
            response_format={"type": "json_object"},
        )
        actions = json.loads(completion.choices[0].message.content).get("actions", [])
    except Exception as exc:
        await openai_client.close()
        return JSONResponse({"error": f"propose failed: {exc}"}, status_code=502)
    propose_s = time.perf_counter() - t0
    await openai_client.close()

    actions = [a for a in actions if a.get("id") and a.get("description")][:5]
    if not actions:
        return JSONResponse({"error": "The language model proposed nothing usable."},
                            status_code=502)

    jev = AsyncTypeSafeClient(api_key=os.environ["TYPESAFE_API_KEY"], model="jev-latest",
                              timeout=60.0)
    t1 = time.perf_counter()
    try:
        decision = await jev.system_one(
            state={"ticket": body.text, "options": actions},
            questions={
                "action": Choice(
                    instructions="Which one of these actions should be taken first?",
                    criteria={a["id"]: a["description"] for a in actions},
                ),
                "risk": Score(
                    instructions="How risky is it to take this action without a human looking first?",
                    criteria=[
                        "Safe to run automatically",
                        "Low risk, log it",
                        "Check with a person first",
                        "Do not act without approval",
                    ],
                ),
            },
        )
    except Exception as exc:
        await jev.aclose()
        return JSONResponse({"error": f"decide failed: {exc}"}, status_code=502)
    decide_s = time.perf_counter() - t1
    await jev.aclose()

    action = decision.answers["action"]
    risk = decision.answers["risk"]
    confidence = action.probabilities.get(action.choice, action.confidence)
    return JSONResponse({
        "actions": actions,
        "propose_seconds": propose_s,
        "decide_seconds": decide_s,
        "chosen": action.choice,
        "confidence": confidence,
        "spread": dict(action.probabilities),
        "risk_score": risk.score,
        "risk_text": (risk.legend or {}).get(
            max(risk.probabilities, key=risk.probabilities.get) if risk.probabilities else 0, ""),
        "gate": "run it" if confidence >= 0.8 and risk.score < 2 else "send to a person",
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
