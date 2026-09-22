"""Video 10 - playing rock paper scissors against a model that only predicts.

Jev never picks a move. It answers one question - what will this person throw
next - and ordinary code plays whatever beats the most likely answer. The
prediction is locked in before you throw, and you can see it afterwards.

    uvicorn app:app --port 8010 --reload
"""

from __future__ import annotations

import random
import threading
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typesafe_sdk import Choice, Noul

import jevlib

MODEL = "jev-latest"
THROWS = ["rock", "paper", "scissors"]
BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}
COUNTER = {"rock": "paper", "paper": "scissors", "scissors": "rock"}

QUESTIONS = {
    "next_throw": Choice(
        instructions=(
            "You are watching someone play rock paper scissors. Their past rounds "
            "are in 'history', oldest first. People repeat throws, follow patterns, "
            "and switch after losing. What will they throw in the next round?"
        ),
        criteria={
            "rock": "They will throw rock.",
            "paper": "They will throw paper.",
            "scissors": "They will throw scissors.",
        },
    ),
    "has_pattern": Noul(
        instructions=(
            "Is there a pattern in how this person is playing, as opposed to "
            "random choices?"
        ),
    ),
}


class Game:
    """One game, kept in memory. Single player, so a single game is enough."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self.lock:
            self.history: list[dict] = []
            self.pending: dict | None = None
            self.wins = self.losses = self.draws = 0
            self.predicted_right = 0
            self.rounds = 0
            self.tokens = 0

    def state_for_model(self) -> dict:
        recent = self.history[-14:]
        return {
            "history": [
                {"round": i + 1, "they_threw": h["you"], "we_threw": h["jev"],
                 "they": h["result_for_you"]}
                for i, h in enumerate(recent)
            ],
            "rounds_played": len(self.history),
        }

    def score(self) -> dict:
        played = self.rounds or 1
        return {
            "rounds": self.rounds,
            "you": self.wins,
            "jev": self.losses,
            "draws": self.draws,
            "jev_win_rate": self.losses / played,
            "prediction_accuracy": self.predicted_right / played,
            "cost": jevlib.jev_cost(self.tokens),
        }


game = Game()
app = FastAPI(title="Rock paper scissors")
jev = jevlib.client(MODEL)


class Throw(BaseModel):
    choice: str


class Simulation(BaseModel):
    rounds: int = 30
    bot: str = "win_stay_lose_shift"


def predict(state: dict) -> dict:
    response = jev.system_one(state=state, questions=QUESTIONS)
    answer = response.answers["next_throw"]
    return {
        "expects": answer.choice,
        "spread": dict(answer.probabilities),
        "confidence": answer.probabilities.get(answer.choice, answer.confidence),
        "pattern": response.answers["has_pattern"].noul,
        "plays": COUNTER[answer.choice],
        "tokens": response.usage.input_tokens,
    }


@app.post("/api/new")
def new_game() -> dict:
    game.reset()
    return game.score()


@app.post("/api/lock")
def lock() -> JSONResponse:
    """Work out the move before the player throws, and keep it hidden."""
    started = time.perf_counter()
    try:
        guess = predict(game.state_for_model())
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
    with game.lock:
        game.pending = guess
        game.tokens += guess["tokens"]
    return JSONResponse({
        "locked": True,
        "seconds": time.perf_counter() - started,
        "rounds_seen": len(game.history),
    })


@app.post("/api/throw")
def throw(body: Throw) -> JSONResponse:
    if body.choice not in THROWS:
        return JSONResponse({"error": "Pick rock, paper or scissors."}, status_code=400)

    with game.lock:
        guess = game.pending
    if guess is None:
        result = lock()
        if isinstance(result, JSONResponse) and result.status_code != 200:
            return result
        with game.lock:
            guess = game.pending

    you, theirs = body.choice, guess["plays"]
    if you == theirs:
        outcome = "draw"
    elif BEATS[you] == theirs:
        outcome = "you"
    else:
        outcome = "jev"

    with game.lock:
        game.rounds += 1
        game.wins += outcome == "you"
        game.losses += outcome == "jev"
        game.draws += outcome == "draw"
        game.predicted_right += guess["expects"] == you
        game.history.append({"you": you, "jev": theirs, "result_for_you": outcome})
        game.pending = None

    return JSONResponse({
        "you": you,
        "jev": theirs,
        "outcome": outcome,
        "expected": guess["expects"],
        "was_right": guess["expects"] == you,
        "spread": guess["spread"],
        "confidence": guess["confidence"],
        "pattern": guess["pattern"],
        "score": game.score(),
        "history": game.history[-12:],
    })


BOTS = {
    "random": "throws at random, with no pattern at all",
    "always_rock": "throws rock every single time",
    "cycle": "rock, paper, scissors, over and over",
    "win_stay_lose_shift": "keeps the throw that won, changes the one that lost",
}

progress = {"done": 0, "total": 0}


@app.get("/api/bots")
def bots() -> dict:
    return {"bots": BOTS, "progress": progress}


@app.post("/api/simulate")
def simulate(body: Simulation) -> JSONResponse:
    """Play a scripted opponent, to see how much of this is pattern and how much
    is luck. Against a truly random opponent nothing can beat one in three."""
    if body.bot not in BOTS:
        return JSONResponse({"error": "Unknown opponent."}, status_code=400)

    rng = random.Random(7)
    history: list[dict] = []
    wins = right = 0
    last_throw = "rock"
    last_result = "draw"
    tokens = 0
    progress.update(done=0, total=body.rounds)
    started = time.perf_counter()

    for round_number in range(body.rounds):
        state = {
            "history": [
                {"round": i + 1, "they_threw": h["you"], "we_threw": h["jev"],
                 "they": h["result_for_you"]}
                for i, h in enumerate(history[-14:])
            ],
            "rounds_played": len(history),
        }
        try:
            guess = predict(state)
        except Exception as exc:
            return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=502)
        tokens += guess["tokens"]

        if body.bot == "random":
            bot_throw = rng.choice(THROWS)
        elif body.bot == "always_rock":
            bot_throw = "rock"
        elif body.bot == "cycle":
            bot_throw = THROWS[round_number % 3]
        else:
            bot_throw = last_throw if last_result == "you" else COUNTER[last_throw]

        theirs = guess["plays"]
        if bot_throw == theirs:
            outcome = "draw"
        elif BEATS[bot_throw] == theirs:
            outcome = "you"
        else:
            outcome = "jev"
            wins += 1
        right += guess["expects"] == bot_throw

        history.append({"you": bot_throw, "jev": theirs, "result_for_you": outcome})
        last_throw, last_result = bot_throw, outcome
        progress["done"] = round_number + 1

    played = body.rounds or 1
    return JSONResponse({
        "bot": body.bot,
        "description": BOTS[body.bot],
        "rounds": body.rounds,
        "jev_wins": wins,
        "jev_win_rate": wins / played,
        "prediction_accuracy": right / played,
        "seconds": time.perf_counter() - started,
        "cost": jevlib.jev_cost(tokens),
        "history": history[-24:],
    })


app.mount("/", StaticFiles(directory="static", html=True), name="static")
