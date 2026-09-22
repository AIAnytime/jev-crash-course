"""Video 8 - browser tests whose assertions are written in English.

Playwright does the clicking. After each step the page's visible text is handed
to Jev, which answers the questions the test cares about: is this an error, would
a customer understand it, can they carry on. The assertion is a probability, so a
test can fail loudly, pass, or say it is not sure.

    uvicorn app:app --port 8008 --reload

The app under test is served from static/shop. Add ?bug=1 to break it on purpose.
"""

from __future__ import annotations

import base64
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul, Score

import jevlib

MODEL = "jev-latest"
BASE = "http://127.0.0.1:8008/shop/index.html"

QUESTIONS = {
    "matches": Noul(
        instructions=(
            "The test expected something to be true of this page, and it is in "
            "'the_test_expects'. Looking only at the page, is that true?"
        ),
    ),
    "state": Choice(
        instructions="What state is this page in right now?",
        criteria={
            "working": "Normal page, nothing has gone wrong.",
            "user_error": "The page is telling the person they need to fix something.",
            "crash": "The page is showing a technical failure, a stack trace or raw error text.",
            "success": "The page is confirming that something completed successfully.",
        },
    ),
    "understandable": Score(
        instructions=(
            "If there is a message on this page, how well would a person with no "
            "technical background understand it?"
        ),
        criteria=[
            "Meaningless to them, technical jargon",
            "They would guess something broke",
            "Mostly clear",
            "Perfectly clear, and says what to do",
        ],
    ),
    "can_continue": Noul(
        instructions="Can the customer carry on and finish what they came to do?",
    ),
}

SCENARIOS = {
    "Add one item to the basket": [
        {"do": "goto", "what": "open the shop",
         "expect": "the basket total at the top of the page reads zero items"},
        {"do": "click", "selector": "[data-add='coffee']", "what": "add the coffee",
         "expect": "the basket total at the top of the page reads one item"},
    ],
    "Check out without filling the form": [
        {"do": "goto", "what": "open the shop",
         "expect": "the page lists products to buy and has a checkout form with an email field and a card field"},
        {"do": "click", "selector": "[data-add='coffee']", "what": "add the coffee",
         "expect": "the basket total at the top of the page reads one item"},
        {"do": "click", "selector": "#pay", "what": "pay with an empty form",
         "expect": "the page asks in plain language for an email address, and shows no technical error text"},
    ],
    "Check out properly": [
        {"do": "goto", "what": "open the shop",
         "expect": "the page lists products to buy and has a checkout form with an email field and a card field"},
        {"do": "click", "selector": "[data-add='oat']", "what": "add the oat milk",
         "expect": "the basket total at the top of the page reads one item"},
        {"do": "fill", "selector": "#email", "value": "sam@example.com",
         "what": "type an email", "expect": "the email field contains sam@example.com"},
        {"do": "fill", "selector": "#card", "value": "4242 4242 4242 4242",
         "what": "type a card number", "expect": "the card field contains a card number"},
        {"do": "click", "selector": "#pay", "what": "pay",
         "expect": "the page confirms the order was placed successfully"},
    ],
}

app = FastAPI(title="Browser tests in English")


class Run(BaseModel):
    scenario: str
    bug: bool = False
    shots: bool = True


def verdict(answers: dict, step: dict) -> dict:
    state = answers["state"]
    matches = answers["matches"].noul
    understandable = answers["understandable"]
    probs = {int(k): v for k, v in (understandable.probabilities or {}).items()}
    legend = {int(k): v for k, v in (understandable.legend or {}).items()}
    level = max(probs, key=probs.get) if probs else round(understandable.score)
    can_continue = answers["can_continue"].noul

    if matches >= 0.8:
        result = "pass"
    elif matches <= 0.35:
        result = "fail"
    else:
        result = "unsure"

    return {
        "result": result,
        "state": state.choice,
        "state_spread": dict(state.probabilities),
        "matches": matches,
        "understandable_score": understandable.score,
        "understandable_word": legend.get(level, str(level)),
        "can_continue": can_continue,
    }


async def snapshot(page) -> str:
    """What the page says, plus what is typed into it. inner_text alone leaves
    out field values, so a test that fills a form would see no change at all."""
    text = await page.inner_text("body")
    fields = await page.evaluate(
        """() => [...document.querySelectorAll('input, textarea, select')]
              .map(el => `${el.id || el.name || el.type}: ${el.value || '(empty)'}`)"""
    )
    if fields:
        text += "\n\nform fields:\n" + "\n".join(fields)
    return text


@app.get("/api/scenarios")
def scenarios() -> dict:
    return {
        "scenarios": {name: [s["what"] for s in steps] for name, steps in SCENARIOS.items()},
        "questions": {
            "matches": "Is what the test expected actually true of this page?",
            "state": "What state is this page in?",
            "understandable": "Would a non-technical person understand the message?",
            "can_continue": "Can the customer carry on?",
        },
    }


@app.post("/api/run")
async def run(body: Run) -> JSONResponse:
    steps = SCENARIOS.get(body.scenario)
    if not steps:
        return JSONResponse({"error": "Unknown scenario."}, status_code=400)

    from playwright.async_api import async_playwright

    url = BASE + ("?bug=1" if body.bug else "")
    jev = jevlib.async_client(MODEL)
    out = []
    started = time.perf_counter()
    tokens = 0

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            page = await browser.new_page(viewport={"width": 900, "height": 700})
            for step in steps:
                action_started = time.perf_counter()
                if step["do"] == "goto":
                    await page.goto(url)
                elif step["do"] == "click":
                    await page.click(step["selector"])
                elif step["do"] == "fill":
                    await page.fill(step["selector"], step["value"])
                await page.wait_for_timeout(120)

                visible = await snapshot(page)
                shot = ""
                if body.shots:
                    shot = base64.b64encode(await page.screenshot()).decode()
                action_s = time.perf_counter() - action_started

                ask_started = time.perf_counter()
                try:
                    response = await jev.system_one(
                        state={"the_test_expects": step["expect"], "page_text": visible},
                        questions=QUESTIONS,
                    )
                    judged = verdict(response.answers, step)
                    tokens += response.usage.input_tokens
                    error = None
                except Exception as exc:
                    judged, error = {}, f"{type(exc).__name__}: {exc}"

                out.append({
                    "what": step["what"],
                    "expect": step["expect"],
                    "page_text": visible,
                    "screenshot": shot,
                    "browser_seconds": action_s,
                    "judge_seconds": time.perf_counter() - ask_started,
                    "error": error,
                    **judged,
                })
            await browser.close()
    except Exception as exc:
        await jev.aclose()
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)
    await jev.aclose()

    failures = [s for s in out if s.get("result") == "fail"]
    unsure = [s for s in out if s.get("result") == "unsure"]
    return JSONResponse({
        "steps": out,
        "seconds": time.perf_counter() - started,
        "judge_seconds": sum(s["judge_seconds"] for s in out),
        "cost": jevlib.jev_cost(tokens),
        "result": "fail" if failures else ("unsure" if unsure else "pass"),
        "url": url,
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
