"""Video 11 - the hosted decision model against the open one you run yourself.

Same four questions, same reviews, same answer key. One engine answers over the
network and bills per token. The other answers on this machine, for nothing,
after a download.

    uvicorn app:app --port 8011 --reload
"""

from __future__ import annotations

import asyncio
import json
import random
import statistics
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import engines
import jevlib
from metrics import accuracy, brier, ece, reliability

HERE = Path(__file__).resolve().parent
REVIEWS = HERE / "data" / "reviews.jsonl"

app = FastAPI(title="Jev vs Laya")
jev = engines.JevEngine()
laya = engines.LayaEngine()

progress = {"done": 0, "total": 0, "stage": ""}

# A line per language, to show where each engine's coverage stops.
LANGUAGE_SAMPLES = [
    {"language": "English", "script": "Latin",
     "text": "Crashes every time I open settings. Third build in a row."},
    {"language": "Spanish", "script": "Latin",
     "text": "La aplicación se cierra sola cuando intento subir una foto."},
    {"language": "German", "script": "Latin",
     "text": "Seit dem Update ist der Akkuverbrauch viel schlimmer geworden."},
    {"language": "Japanese", "script": "Japanese",
     "text": "アップデート後、アプリが起動しなくなりました。"},
    {"language": "Hindi", "script": "Devanagari",
     "text": "ऐप खोलते ही बंद हो जाता है। बहुत खराब।"},
    {"language": "Arabic", "script": "Arabic",
     "text": "التطبيق يتوقف عن العمل في كل مرة أفتحها."},
]


def load_reviews() -> list[dict]:
    rows = []
    with REVIEWS.open() as handle:
        for line in handle:
            row = json.loads(line)
            stars = row["stars"]
            row["true_sentiment"] = (
                "negative" if stars <= 2 else "neutral" if stars == 3 else "positive")
            rows.append(row)
    return rows


ALL_REVIEWS = load_reviews()


class Ask(BaseModel):
    text: str


class Bench(BaseModel):
    n: int = 40
    seed: int = 0
    concurrency: int = 20


@app.get("/api/config")
def config() -> dict:
    return {
        "jev_ready": jev.ready,
        "laya_loaded": laya.ready,
        "laya_device": laya.device,
        "laya_error": laya.error,
        "reviews": len(ALL_REVIEWS),
        "questions": [
            {"key": q["key"], "kind": q["kind"], "instructions": q["instructions"]}
            for q in engines.QUESTIONS
        ],
        "languages": [
            {"language": s["language"], "script": s["script"], "text": s["text"]}
            for s in LANGUAGE_SAMPLES
        ],
    }


@app.get("/api/progress")
def read_progress() -> dict:
    return progress


@app.post("/api/warm")
async def warm() -> JSONResponse:
    """Pull the weights in and keep them in memory. The first call does the
    downloading, so it can take minutes; every call after it is local compute."""
    started = time.perf_counter()
    try:
        await asyncio.to_thread(laya.agent, "english")
    except Exception as exc:
        laya.error = f"{type(exc).__name__}: {exc}"
        return JSONResponse({"error": laya.error}, status_code=500)
    return JSONResponse({
        "loaded": True,
        "seconds": time.perf_counter() - started,
        "device": laya.device,
    })


@app.post("/api/ask")
async def ask(body: Ask) -> JSONResponse:
    """One review, both engines, side by side."""
    out = {}

    async def run_jev():
        try:
            out["jev"] = await jev.ask_async(body.text)
        except Exception as exc:
            out["jev"] = {"error": f"{type(exc).__name__}: {exc}"}

    async def run_laya():
        try:
            out["laya"] = await asyncio.to_thread(laya.ask, body.text)
        except Exception as exc:
            out["laya"] = {"error": f"{type(exc).__name__}: {exc}"}

    await asyncio.gather(run_jev(), run_laya())
    await jev.aclose()

    agreement = {}
    if "error" not in out.get("jev", {}) and "error" not in out.get("laya", {}):
        for key in engines.BY_KEY:
            a = out["jev"]["answers"].get(key)
            b = out["laya"]["answers"].get(key)
            if a and b:
                agreement[key] = a["value"] == b["value"]
    return JSONResponse({**out, "agreement": agreement})


def score_lane(rows: list[dict], answers: list[dict]) -> dict:
    """Sentiment against the star rating neither engine was shown."""
    pairs = []
    for row, answer in zip(rows, answers):
        got = (answer.get("answers") or {}).get("sentiment")
        if not got:
            continue
        pairs.append((float(got["confidence"]), got["value"] == row["true_sentiment"]))
    latencies = [a["seconds"] for a in answers if "error" not in a]
    return {
        "n": len(pairs),
        "accuracy": accuracy(pairs) if pairs else 0.0,
        "ece": ece(pairs) if pairs else 0.0,
        "brier": brier(pairs) if pairs else 0.0,
        "bins": [
            {"lo": b.lo, "hi": b.hi, "n": b.n,
             "confidence": b.mean_confidence, "accuracy": b.accuracy}
            for b in reliability(pairs)
        ] if pairs else [],
        "median_call": statistics.median(latencies) if latencies else 0.0,
        "slowest_call": max(latencies) if latencies else 0.0,
        "errors": sum(1 for a in answers if "error" in a),
    }


@app.post("/api/bench")
async def bench(body: Bench) -> JSONResponse:
    """Both engines over the same reviews.

    Jev runs concurrently, because that is how you would use a hosted API. Laya
    runs one at a time, because that is what a single local model does. The
    per-call medians are the fair comparison; the wall clocks are what each
    setup actually gives you.
    """
    rows = list(ALL_REVIEWS)
    random.Random(body.seed).shuffle(rows)
    rows = rows[: max(1, min(body.n, len(rows)))]
    progress.update(done=0, total=len(rows) * 2, stage="starting")

    if not laya.ready:
        try:
            progress["stage"] = "loading laya"
            await asyncio.to_thread(laya.agent, "english")
        except Exception as exc:
            return JSONResponse({"error": f"Laya failed to load: {exc}"}, status_code=500)

    semaphore = asyncio.Semaphore(body.concurrency)

    async def one_jev(row: dict) -> dict:
        async with semaphore:
            try:
                result = await jev.ask_async(row["text"])
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}", "seconds": 0.0}
            progress["done"] += 1
            return result

    progress["stage"] = "Jev, over the network"
    jev_started = time.perf_counter()
    jev_answers = await asyncio.gather(*(one_jev(r) for r in rows))
    jev_wall = time.perf_counter() - jev_started
    await jev.aclose()

    def all_laya() -> list[dict]:
        out = []
        for row in rows:
            try:
                out.append(laya.ask(row["text"]))
            except Exception as exc:
                out.append({"error": f"{type(exc).__name__}: {exc}", "seconds": 0.0})
            progress["done"] += 1
        return out

    progress["stage"] = "Laya, on this machine"
    laya_started = time.perf_counter()
    laya_answers = await asyncio.to_thread(all_laya)
    laya_wall = time.perf_counter() - laya_started
    progress["stage"] = "done"

    jev_score = score_lane(rows, jev_answers)
    laya_score = score_lane(rows, laya_answers)
    jev_score.update(wall=jev_wall, cost=sum(a.get("cost", 0) for a in jev_answers),
                     label=jev.label, where=jev.where, concurrency=body.concurrency)
    laya_score.update(wall=laya_wall, cost=0.0, label=laya.label, where=laya.where,
                      concurrency=1, device=laya.device)

    agree = {}
    for key in engines.BY_KEY:
        both = [
            ((a.get("answers") or {}).get(key), (b.get("answers") or {}).get(key))
            for a, b in zip(jev_answers, laya_answers)
        ]
        both = [(a, b) for a, b in both if a and b]
        agree[key] = (sum(1 for a, b in both if a["value"] == b["value"]) / len(both)
                      if both else 0.0)

    samples = []
    for row, a, b in list(zip(rows, jev_answers, laya_answers))[:40]:
        if "error" in a or "error" in b:
            continue
        samples.append({
            "text": row["text"][:180],
            "stars": row["stars"],
            "truth": row["true_sentiment"],
            "jev": a["answers"]["sentiment"],
            "laya": b["answers"]["sentiment"],
        })

    return JSONResponse({
        "rows": len(rows),
        "jev": jev_score,
        "laya": laya_score,
        "agreement": agree,
        "samples": samples,
    })


@app.post("/api/languages")
async def languages() -> JSONResponse:
    """The same complaint in six languages, through both engines.

    Laya ships a separate multilingual checkpoint; its English one is documented
    as failing outside Latin script, so both are run here.
    """
    out = []
    for sample in LANGUAGE_SAMPLES:
        row = {"language": sample["language"], "script": sample["script"],
               "text": sample["text"]}
        try:
            row["jev"] = await jev.ask_async(sample["text"])
        except Exception as exc:
            row["jev"] = {"error": f"{type(exc).__name__}: {exc}"}
        for which in ("english", "multilingual"):
            try:
                row[f"laya_{which}"] = await asyncio.to_thread(laya.ask, sample["text"], which)
            except Exception as exc:
                row[f"laya_{which}"] = {"error": f"{type(exc).__name__}: {exc}"}
        out.append(row)
    await jev.aclose()
    return JSONResponse({"rows": out})


app.mount("/", StaticFiles(directory="static", html=True), name="static")
