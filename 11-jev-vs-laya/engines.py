"""One question set, two engines.

The questions are written once, in plain dictionaries, and rendered into
whichever shape each engine wants. Jev takes typed objects over HTTP. Laya takes
dictionaries and runs in this process, on this machine.
"""

from __future__ import annotations

import threading
import time
import warnings

import jevlib

JEV_MODEL = "jev-latest"
LAYA_REPO = "convaiinnovations/laya"

# The same four questions project 04 uses, so the answer key is the same too:
# the reviewer's own star rating, which neither engine is shown.
QUESTIONS = [
    {
        "key": "sentiment",
        "kind": "choice",
        "instructions": "What is the reviewer's overall feeling about the app?",
        "criteria": {
            "positive": "Broadly happy with it.",
            "neutral": "Mixed or factual, with no clear lean.",
            "negative": "Broadly unhappy with it.",
        },
    },
    {
        "key": "topic",
        "kind": "choice",
        "instructions": "What is this review mainly about?",
        "criteria": {
            "performance": "Speed, battery, crashes on load, lag.",
            "ui": "Layout, design, navigation, ease of use.",
            "features": "A capability that exists, is missing, or is wanted.",
            "pricing": "Cost, ads, subscriptions, purchases.",
            "bugs": "Something is broken or behaves incorrectly.",
            "other": "None of the above fits.",
        },
    },
    {
        "key": "is_bug",
        "kind": "noul",
        "instructions": (
            "Does this review report a concrete defect an engineer could act on? "
            "A request for a new feature does not count."
        ),
    },
    {
        "key": "churn_risk",
        "kind": "score",
        "instructions": "How likely is this reviewer to stop using the app?",
        "criteria": [
            "Committed, recommends it to others",
            "Satisfied, no sign of leaving",
            "Irritated but still using it",
            "Frustrated, looking at alternatives",
            "Has left or says they are leaving",
        ],
    },
]

BY_KEY = {q["key"]: q for q in QUESTIONS}


def as_jev_questions() -> dict:
    from typesafe_sdk import Choice, Noul, Score

    out = {}
    for q in QUESTIONS:
        if q["kind"] == "choice":
            out[q["key"]] = Choice(instructions=q["instructions"], criteria=q["criteria"])
        elif q["kind"] == "noul":
            out[q["key"]] = Noul(instructions=q["instructions"])
        else:
            out[q["key"]] = Score(instructions=q["instructions"], criteria=q["criteria"])
    return out


def as_laya_questions() -> dict:
    out = {}
    for q in QUESTIONS:
        item = {"type": q["kind"], "instructions": q["instructions"]}
        if q["kind"] != "noul":
            item["criteria"] = q["criteria"]
        out[q["key"]] = item
    return out


def _normalise_choice(value, confidence, probabilities) -> dict:
    probabilities = {str(k): float(v) for k, v in (probabilities or {}).items()}
    return {
        "kind": "choice",
        "value": value,
        "confidence": float(probabilities.get(str(value), confidence or 0.0)),
        "probabilities": probabilities,
    }


def _normalise_noul(p: float) -> dict:
    p = float(p)
    return {
        "kind": "noul",
        "value": "yes" if p >= 0.5 else "no",
        "confidence": max(p, 1 - p),
        "probability": p,
        "probabilities": {"yes": p, "no": 1 - p},
    }


def _normalise_score(score, confidence, probabilities, levels) -> dict:
    probabilities = {int(k): float(v) for k, v in (probabilities or {}).items()}
    level = (max(probabilities, key=probabilities.get) if probabilities
             else int(round(float(score))))
    level = max(0, min(level, len(levels) - 1))
    return {
        "kind": "score",
        "value": levels[level],
        "level": level,
        "score": float(score),
        "confidence": float(probabilities.get(level, confidence or 0.0)),
        "probabilities": {levels[k]: v for k, v in probabilities.items() if k < len(levels)},
    }


class JevEngine:
    """The hosted one. Every call is a network round trip."""

    name = "jev"
    label = "Jev"
    where = "hosted API"

    def __init__(self) -> None:
        self.questions = as_jev_questions()
        self._client = None
        self._async_client = None

    @property
    def ready(self) -> bool:
        try:
            jevlib.jev_key()
            return True
        except RuntimeError:
            return False

    def client(self):
        if self._client is None:
            self._client = jevlib.client(JEV_MODEL)
        return self._client

    def async_client(self):
        if self._async_client is None:
            self._async_client = jevlib.async_client(JEV_MODEL)
        return self._async_client

    def unpack(self, response) -> dict:
        answers = {}
        for q in QUESTIONS:
            a = response.answers.get(q["key"])
            if a is None:
                continue
            if q["kind"] == "choice":
                answers[q["key"]] = _normalise_choice(a.choice, a.confidence, a.probabilities)
            elif q["kind"] == "noul":
                answers[q["key"]] = _normalise_noul(a.noul)
            else:
                answers[q["key"]] = _normalise_score(
                    a.score, a.confidence, a.probabilities, q["criteria"])
        return answers

    def ask(self, text: str) -> dict:
        started = time.perf_counter()
        response = self.client().system_one(state={"review": text}, questions=self.questions)
        return {
            "seconds": time.perf_counter() - started,
            "answers": self.unpack(response),
            "input_tokens": response.usage.input_tokens,
            "cost": jevlib.jev_cost(response.usage.input_tokens),
        }

    async def ask_async(self, text: str) -> dict:
        started = time.perf_counter()
        response = await self.async_client().system_one(
            state={"review": text}, questions=self.questions)
        return {
            "seconds": time.perf_counter() - started,
            "answers": self.unpack(response),
            "input_tokens": response.usage.input_tokens,
            "cost": jevlib.jev_cost(response.usage.input_tokens),
        }

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.aclose()
            self._async_client = None


class LayaEngine:
    """The local one. Weights on disk, no network, no per-call cost.

    The first load pulls the weights from Hugging Face and takes a while. After
    that the model sits in memory and every call is local compute.
    """

    name = "laya"
    label = "Laya"
    where = "on this machine"

    def __init__(self) -> None:
        self.questions = as_laya_questions()
        self._agents: dict[str, object] = {}
        self._lock = threading.Lock()
        self.device = None
        self.error = None

    @property
    def ready(self) -> bool:
        return "english" in self._agents

    def agent(self, which: str = "english"):
        """Load a checkpoint once, then reuse it. Guarded by a lock because a
        model loading twice at once would use twice the memory."""
        with self._lock:
            if which in self._agents:
                return self._agents[which]
            warnings.filterwarnings("ignore")
            import laya

            started = time.perf_counter()
            if which == "multilingual":
                agent = laya.load(LAYA_REPO, subfolder="multilingual")
            else:
                agent = laya.load(LAYA_REPO)
            self.device = str(getattr(agent, "device", "cpu"))
            self._agents[which] = agent
            self.load_seconds = time.perf_counter() - started
            return agent

    def unpack(self, result: dict) -> dict:
        answers = {}
        for q in QUESTIONS:
            a = (result.get("answers") or {}).get(q["key"])
            if a is None:
                continue
            if q["kind"] == "choice":
                answers[q["key"]] = _normalise_choice(
                    a.get("choice"), a.get("confidence"), a.get("probabilities"))
            elif q["kind"] == "noul":
                answers[q["key"]] = _normalise_noul(a.get("noul", 0.5))
            else:
                probabilities = a.get("probabilities")
                if not probabilities and a.get("distribution") is not None:
                    probabilities = {i: p for i, p in enumerate(a["distribution"])}
                answers[q["key"]] = _normalise_score(
                    a.get("score", 0.0), a.get("confidence"), probabilities, q["criteria"])
        return answers

    def ask(self, text: str, which: str = "english") -> dict:
        agent = self.agent(which)
        started = time.perf_counter()
        result = agent.predict({"review": text}, self.questions)
        return {
            "seconds": time.perf_counter() - started,
            "answers": self.unpack(result),
            "input_tokens": 0,
            "cost": 0.0,
            "checkpoint": which,
        }
