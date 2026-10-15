"""A content crew with a decision model holding both ends.

Before the crew runs, Jev reads the brief and decides whether it is worth
spending an LLM on. After every draft, Jev scores it and decides: publish, send
it back, or stop. That verdict is the loop condition, which is the whole point.
An LLM judging its own output costs seconds and cents per lap. This costs
milliseconds, and it returns a number you can put a threshold on.

The agents never see Jev. They get an instruction built from its numbers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from typesafe_sdk import Choice, Noul, Score

import jevlib
from tools import Collector, WebSearch, search_available

JEV_MODEL = "jev-latest"
LLM_MODEL = "openai/gpt-4.1-mini"
# Swap the writer and the same gate gives a different answer. gpt-4o-mini
# typically stalls around 0.65 on on_brief; gpt-4.1-mini clears it first time.
LLM_MODELS = ["openai/gpt-4.1-mini", "openai/gpt-4o-mini", "openai/gpt-4o", "openai/gpt-4.1"]
# gpt-4o-mini list price, dollars per 1M tokens.
LLM_IN, LLM_OUT = 0.15, 0.60

# --- what Jev is asked, in two places -------------------------------------

BRIEF_QUESTIONS = {
    "clear_enough": Noul(
        instructions=(
            "Is this brief specific enough to write a useful article from, without "
            "going back to the requester for more detail?"
        ),
    ),
    "needs_research": Noul(
        instructions=(
            "Would this need current facts, numbers or sources from the web, as "
            "opposed to being writable from general knowledge?"
        ),
    ),
    "audience": Choice(
        instructions="Who is this piece for?",
        criteria={
            "developers": "People who will read code and care about how it works.",
            "executives": "People deciding on budget, risk and direction.",
            "general": "A broad audience with no special background.",
        },
    ),
    "depth": Score(
        instructions="How much depth does this brief call for?",
        criteria=[
            "A short note, a few paragraphs",
            "A standard post",
            "A detailed guide",
            "A deep technical piece",
        ],
    ),
}

DRAFT_QUESTIONS = {
    "on_brief": Noul(
        instructions="Does the draft actually deliver what the brief asked for?",
    ),
    "grounded": Noul(
        instructions=(
            "Does the draft stay within the supplied research? Answer no if it "
            "states specific facts, numbers or quotes that the research does not "
            "support."
        ),
    ),
    "clarity": Score(
        instructions="How easy is this to follow on one read?",
        criteria=[
            "Confusing, I had to reread it",
            "Takes effort to follow",
            "Mostly clear",
            "Immediately clear",
        ],
    ),
    "hype": Score(
        instructions="How much marketing language is in it?",
        criteria=[
            "Plain and factual",
            "Mild enthusiasm",
            "Noticeably promotional",
            "Pure hype",
        ],
    ),
}

# What "good enough to publish" means, in one place so it is arguable.
THRESHOLDS = {
    "on_brief": 0.75,
    "grounded": 0.75,
    "clarity_min": 2.0,
    "hype_max": 1.5,
}


@dataclass
class Spend:
    """Who used what. The split is the story, so it is tracked per side."""

    jev_calls: int = 0
    jev_tokens: int = 0
    jev_seconds: float = 0.0
    llm_calls: int = 0
    llm_in: int = 0
    llm_out: int = 0
    llm_seconds: float = 0.0

    @property
    def jev_cost(self) -> float:
        return jevlib.jev_cost(self.jev_tokens)

    @property
    def llm_cost(self) -> float:
        return self.llm_in / 1e6 * LLM_IN + self.llm_out / 1e6 * LLM_OUT

    def as_dict(self) -> dict:
        return {
            "jev": {"calls": self.jev_calls, "tokens": self.jev_tokens,
                    "seconds": self.jev_seconds, "cost": self.jev_cost},
            "llm": {"calls": self.llm_calls, "in": self.llm_in, "out": self.llm_out,
                    "seconds": self.llm_seconds, "cost": self.llm_cost},
        }


def _score(answer, levels: list[str]) -> dict:
    probs = {int(k): v for k, v in (answer.probabilities or {}).items()}
    level = max(probs, key=probs.get) if probs else round(answer.score)
    level = max(0, min(level, len(levels) - 1))
    return {"score": answer.score, "level": level, "value": levels[level],
            "confidence": probs.get(level, answer.confidence)}


def read_brief(client, brief: str, spend: Spend) -> dict:
    started = time.perf_counter()
    response = client.system_one(state={"brief": brief}, questions=BRIEF_QUESTIONS)
    elapsed = time.perf_counter() - started
    spend.jev_calls += 1
    spend.jev_tokens += response.usage.input_tokens
    spend.jev_seconds += elapsed

    a = response.answers
    audience = a["audience"]
    depth = _score(a["depth"], BRIEF_QUESTIONS["depth"].criteria)
    return {
        "seconds": elapsed,
        "clear_enough": a["clear_enough"].noul,
        "needs_research": a["needs_research"].noul,
        "audience": audience.choice,
        "audience_confidence": audience.probabilities.get(audience.choice, audience.confidence),
        "audience_spread": dict(audience.probabilities),
        "depth": depth,
        "proceed": a["clear_enough"].noul >= 0.5,
    }


def judge_draft(client, brief: str, research: str, draft: str, spend: Spend,
                has_research: bool = True) -> dict:
    """Score a draft and decide whether the loop turns again.

    The grounding question is only asked when there is research to be grounded
    in. Asked against an empty research note it scores about 0.15 whatever the
    draft says, because nothing can be supported by nothing, and the loop then
    never converges.
    """
    questions = dict(DRAFT_QUESTIONS)
    if not has_research:
        questions.pop("grounded")

    state = {"brief": brief, "draft": draft}
    if has_research:
        state["research"] = research[:6000]

    started = time.perf_counter()
    response = client.system_one(state=state, questions=questions)
    elapsed = time.perf_counter() - started
    spend.jev_calls += 1
    spend.jev_tokens += response.usage.input_tokens
    spend.jev_seconds += elapsed

    a = response.answers
    clarity = _score(a["clarity"], DRAFT_QUESTIONS["clarity"].criteria)
    hype = _score(a["hype"], DRAFT_QUESTIONS["hype"].criteria)
    scores = {
        "on_brief": a["on_brief"].noul,
        "grounded": a["grounded"].noul if has_research else None,
        "clarity": clarity,
        "hype": hype,
    }

    # Which dials failed, in words the editor can act on, with the number that
    # failed so the reason is arguable rather than a vibe.
    problems = []
    if scores["on_brief"] < THRESHOLDS["on_brief"]:
        problems.append(
            f"It does not fully deliver the brief ({scores['on_brief']:.2f}, needs "
            f"{THRESHOLDS['on_brief']:.2f}). Go through the brief one clause at a "
            "time and make sure each one is covered explicitly.")
    if has_research and scores["grounded"] < THRESHOLDS["grounded"]:
        problems.append(
            f"It states things the research does not support ({scores['grounded']:.2f}, "
            f"needs {THRESHOLDS['grounded']:.2f}). Remove or soften any specific fact, "
            "number or quote you cannot point at a source for.")
    if clarity["score"] < THRESHOLDS["clarity_min"]:
        problems.append(
            f"It is hard to follow (clarity {clarity['score']:.2f}, needs "
            f"{THRESHOLDS['clarity_min']:.2f}). Shorter sentences, one idea per "
            "paragraph, and put the point first.")
    if hype["score"] > THRESHOLDS["hype_max"]:
        problems.append(
            f"It reads as marketing (hype {hype['score']:.2f}, must be under "
            f"{THRESHOLDS['hype_max']:.2f}). Cut the superlatives and keep the specifics.")

    fatal = scores["on_brief"] < 0.35 or (has_research and scores["grounded"] < 0.35)
    verdict = "publish" if not problems else ("stop" if fatal else "rewrite")
    return {"seconds": elapsed, "scores": scores, "problems": problems,
            "verdict": verdict, "has_research": has_research}


def distance_from_passing(scores: dict) -> float:
    """How far this draft is from clearing every threshold. Used to notice when a
    rewrite is not actually helping, so the loop can stop instead of paying for
    another lap."""
    gap = 0.0
    gap += max(0.0, THRESHOLDS["on_brief"] - scores["on_brief"])
    if scores.get("grounded") is not None:
        gap += max(0.0, THRESHOLDS["grounded"] - scores["grounded"])
    gap += max(0.0, THRESHOLDS["clarity_min"] - scores["clarity"]["score"]) / 3
    gap += max(0.0, scores["hype"]["score"] - THRESHOLDS["hype_max"]) / 3
    return gap


# --- the crew --------------------------------------------------------------

def build_llm(model: str | None = None):
    from crewai import LLM

    return LLM(model=model or LLM_MODEL, base_url=jevlib.openai_base_url(),
               api_key=jevlib.openai_key(), temperature=0.4, max_tokens=1200)


def run_research(brief: str, collector: Collector, spend: Spend,
                 model: str | None = None) -> str:
    """Researcher agent. The only agent with a tool."""
    from crewai import Agent, Crew, Task

    llm = build_llm(model)
    researcher = Agent(
        role="Researcher",
        goal="Find current, specific, citable material for the brief",
        backstory=(
            "You gather facts. You search, you read, and you write up what you "
            "found with the source next to each point. You never pad."
        ),
        tools=[WebSearch(collector=collector)],
        llm=llm, verbose=False, max_iter=4,
    )
    task = Task(
        description=(
            f"Research this brief:\n\n{brief}\n\n"
            "Search for current information. Write up the findings as short bullet "
            "points, each with the source url it came from. Facts only."
        ),
        expected_output="Bullet points of findings, each with a source url.",
        agent=researcher,
    )
    return _kickoff(Crew(agents=[researcher], tasks=[task], verbose=False), spend)


def run_writer(brief: str, research: str, audience: str, depth: str, spend: Spend,
               has_research: bool = True, model: str | None = None) -> str:
    from crewai import Agent, Crew, Task

    llm = build_llm(model)
    writer = Agent(
        role="Writer",
        goal="Turn the brief into a piece that does what it asked for",
        backstory=(
            "You write plainly for a specific reader. You cover every part of the "
            "brief. You do not write marketing copy."
        ),
        llm=llm, verbose=False,
    )
    if has_research:
        sourcing = (
            f"Research to work from:\n{research}\n\n"
            "Use only what is in the research. No invented numbers, no invented quotes."
        )
    else:
        # Telling it to use only the research when there is none produces a thin,
        # hedged draft that never satisfies the brief.
        sourcing = (
            "There is no research for this one, so write from what you already know. "
            "Do not invent specific numbers, quotes or citations."
        )
    task = Task(
        description=(
            f"Brief:\n{brief}\n\nAudience: {audience}\nLength: {depth}\n\n"
            f"{sourcing}\n\n"
            "Cover every part of the brief explicitly. If the brief asks for two "
            "things, the piece must clearly do both. Plain language, no marketing tone."
        ),
        expected_output="The finished piece, in markdown.",
        agent=writer,
    )
    return _kickoff(Crew(agents=[writer], tasks=[task], verbose=False), spend)


def run_editor(brief: str, research: str, draft: str, problems: list[str], spend: Spend,
               has_research: bool = True, model: str | None = None) -> str:
    """The rewrite. Its instructions are Jev's failed dials, in words."""
    from crewai import Agent, Crew, Task

    llm = build_llm(model)
    editor = Agent(
        role="Editor",
        goal="Fix exactly the problems you are given, and change nothing else",
        backstory=(
            "You are given a draft and a specific list of what is wrong with it. "
            "You fix those things. You do not rewrite from scratch and you do not "
            "add new claims."
        ),
        llm=llm, verbose=False,
    )
    numbered = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(problems))
    sourcing = (f"Research:\n{research}\n\n" if has_research else "")
    limit = ("Do not add claims the research does not support."
             if has_research else
             "Do not invent specific numbers, quotes or citations.")
    task = Task(
        description=(
            f"Brief:\n{brief}\n\n{sourcing}Current draft:\n{draft}\n\n"
            f"A reviewer flagged these problems:\n{numbered}\n\n"
            f"Fix them. Keep everything that already works. {limit}"
        ),
        expected_output="The revised piece, in markdown.",
        agent=editor,
    )
    return _kickoff(Crew(agents=[editor], tasks=[task], verbose=False), spend)


def _kickoff(crew, spend: Spend) -> str:
    started = time.perf_counter()
    result = crew.kickoff()
    spend.llm_seconds += time.perf_counter() - started
    usage = getattr(result, "token_usage", None)
    if usage is not None:
        spend.llm_calls += getattr(usage, "successful_requests", 1) or 1
        spend.llm_in += getattr(usage, "prompt_tokens", 0) or 0
        spend.llm_out += getattr(usage, "completion_tokens", 0) or 0
    return str(result).strip()


BRIEFS = [
    "Explain to a developer audience what a 'System 1' decision model is, how it "
    "differs from an LLM, and when you would reach for one. Include current "
    "examples of models in this category.",
    "Write a short post for engineering managers on what prompt injection is and "
    "what actually mitigates it in production.",
    "Something about AI.",
]
