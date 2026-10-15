"""Video 12 - a CrewAI pipeline with a decision model at both ends.

    uvicorn app:app --port 8012 --reload

Stages are streamed to the page as they finish, because the interesting part is
watching the loop turn: draft, judged, rewritten, judged again.
"""

from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

import jevlib
import pipeline
from tools import Collector, search_available

app = FastAPI(title="Agent crew with Jev")



@app.middleware("http")
async def no_store(request, call_next):
    """These are demo apps that get edited while they are running. Without this,
    a browser happily serves you yesterday's app.js against today's server."""
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/api/config")
def config() -> dict:
    return {
        "jev": _has(jevlib.jev_key),
        "llm": _has(jevlib.openai_key),
        "search": search_available(),
        "llm_model": pipeline.LLM_MODEL,
        "llm_models": pipeline.LLM_MODELS,
        "jev_model": pipeline.JEV_MODEL,
        "briefs": pipeline.BRIEFS,
        "thresholds": pipeline.THRESHOLDS,
        "brief_questions": [
            {"key": k, "kind": _kind(v), "instructions": v.instructions}
            for k, v in pipeline.BRIEF_QUESTIONS.items()
        ],
        "draft_questions": [
            {"key": k, "kind": _kind(v), "instructions": v.instructions}
            for k, v in pipeline.DRAFT_QUESTIONS.items()
        ],
    }


def _has(fn) -> bool:
    try:
        fn()
        return True
    except RuntimeError:
        return False


def _kind(question) -> str:
    return type(question).__name__.lower()


def sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/api/run")
async def run(brief: str, max_rounds: int = 3, model: str = pipeline.LLM_MODEL):
    async def events():
        brief_text = brief.strip()
        if not brief_text:
            yield sse({"stage": "error", "message": "Give it a brief."})
            return

        spend = pipeline.Spend()
        collector = Collector()
        started = time.perf_counter()
        client = jevlib.client(pipeline.JEV_MODEL)

        # 1. Jev reads the brief, before a single LLM token is spent.
        yield sse({"stage": "gate_start", "model": model})
        try:
            gate = await asyncio.to_thread(pipeline.read_brief, client, brief_text, spend)
        except Exception as exc:
            yield sse({"stage": "error", "message": f"{type(exc).__name__}: {exc}"})
            return
        yield sse({"stage": "gate", "data": gate, "spend": spend.as_dict()})

        if not gate["proceed"]:
            yield sse({
                "stage": "done", "verdict": "blocked", "rounds": 0,
                "reason": "The brief is too vague to write from, so the crew never ran.",
                "spend": spend.as_dict(), "elapsed": time.perf_counter() - started,
                "final": "", "sources": collector.snapshot(),
            })
            return

        # 2. The crew. Research first, but only if it is that kind of brief.
        research = "No research was gathered; this brief did not call for it."
        has_research = gate["needs_research"] >= 0.5
        if has_research:
            yield sse({"stage": "research_start", "search_available": search_available()})
            try:
                research = await asyncio.to_thread(
                    pipeline.run_research, brief_text, collector, spend, model)
            except Exception as exc:
                yield sse({"stage": "error", "message": f"research failed: {exc}"})
                return
            yield sse({"stage": "research", "notes": research,
                       "sources": collector.snapshot(), "spend": spend.as_dict()})

        depth = gate["depth"]["value"]
        yield sse({"stage": "writing", "round": 1})
        try:
            draft = await asyncio.to_thread(
                pipeline.run_writer, brief_text, research, gate["audience"], depth, spend,
                has_research, model)
        except Exception as exc:
            yield sse({"stage": "error", "message": f"writing failed: {exc}"})
            return

        # 3. The loop. Jev decides whether it turns again.
        verdict = None
        rounds = 0
        history = []
        previous_gap = None
        for round_number in range(1, max_rounds + 1):
            rounds = round_number
            yield sse({"stage": "draft", "round": round_number, "text": draft,
                       "spend": spend.as_dict()})
            try:
                judged = await asyncio.to_thread(
                    pipeline.judge_draft, client, brief_text, research, draft, spend,
                    has_research)
            except Exception as exc:
                yield sse({"stage": "error", "message": f"judging failed: {exc}"})
                return
            history.append({"round": round_number, **judged["scores"]})
            verdict = judged["verdict"]
            yield sse({"stage": "judged", "round": round_number, **judged,
                       "spend": spend.as_dict()})

            if verdict in ("publish", "stop") or round_number == max_rounds:
                break

            # If the last rewrite did not move the draft any closer to passing,
            # stop. Another lap costs another LLM call and buys nothing.
            gap = pipeline.distance_from_passing(judged["scores"])
            if previous_gap is not None and gap >= previous_gap - 0.02:
                verdict = "stalled"
                yield sse({"stage": "stalled", "round": round_number,
                           "gap": gap, "previous_gap": previous_gap})
                break
            previous_gap = gap

            yield sse({"stage": "rewriting", "round": round_number + 1,
                       "problems": judged["problems"]})
            try:
                draft = await asyncio.to_thread(
                    pipeline.run_editor, brief_text, research, draft,
                    judged["problems"], spend, has_research, model)
            except Exception as exc:
                yield sse({"stage": "error", "message": f"rewrite failed: {exc}"})
                return

        yield sse({
            "stage": "done",
            "verdict": {
                "publish": "publish",
                "stop": "stop",
                "stalled": "needs a human",
            }.get(verdict, "out of rounds"),
            "rounds": rounds,
            "history": history,
            "final": draft,
            "sources": collector.snapshot(),
            "spend": spend.as_dict(),
            "elapsed": time.perf_counter() - started,
        })

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


app.mount("/", StaticFiles(directory="static", html=True), name="static")
