# 12 - A crew of agents with a decision gate

Three CrewAI agents research, write and edit. A decision model holds both ends of
the pipeline:

- **Before anything runs**, Jev reads the brief and decides whether it is worth
  spending an LLM on at all, who the audience is, how deep to go, and whether the
  piece needs live research.
- **After every draft**, Jev scores it on four dials and decides: publish, send it
  back, or stop. That verdict is the loop condition.

The agents never see Jev. When a draft comes back, the editor is handed an
instruction built from the dials that failed, with the numbers in it.

## Run

This project has **its own virtual environment**, because CrewAI pins older
versions of `openai` and `pydantic` than the other projects need.

```bash
cd 12-agent-crew
uv venv .venv --python 3.12          # or: python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app:app --port 8012 --reload
```

Open http://localhost:8012, and http://localhost:8012/whiteboard.html for the
boards.

Keys, all in the repo-root `.env`: `JEV_API_KEY`, `OPENAI_API_KEY`, and
`TAVILY_API_KEY` for web search. Without the Tavily key the researcher falls back
to what the model already knows and the page says so.

## The two question sets

Read the brief, before any spend:

| Question | Type |
|---|---|
| Is this brief specific enough to write from? | yes/no |
| Would this need current facts from the web? | yes/no |
| Who is this for? | pick one |
| How much depth does it call for? | score |

Judge the draft, on every lap:

| Question | Type | Publishes at |
|---|---|---|
| Does it deliver what the brief asked for? | yes/no | 0.75 |
| Does it stay within the research? | yes/no | 0.75 |
| How easy is it to follow? | score | 2.0 of 3 |
| How much marketing language? | score | under 1.5 |

Thresholds live in `THRESHOLDS` in `pipeline.py`, in one place, so they are
arguable rather than buried.

## Measured

| | |
|---|---|
| vague brief, blocked at the gate | $0.00002, 1.0s, zero LLM calls |
| real brief, with web research | published on round 1, 23.3s, 5 sources |
| that run, Jev | 2 calls, 2.0s, $0.000116 |
| that run, the crew | 3 calls, 21.3s, $0.00135 |

So on a full run the decision model is about 8% of the cost and 9% of the time.
On the blocked brief it is 100% of a very small bill, which is the point.

One run each, one afternoon. Re-run before quoting.

## Two things worth knowing

**The grounding question is only asked when there is research.** Asked against an
empty research note it scores about 0.15 no matter what the draft says, because
nothing can be supported by nothing, and the loop then never converges. This
caught me during the build.

**Swap the writer model and the same gate gives a different answer.** On the
prompt-injection brief, `gpt-4.1-mini` clears on-brief at 0.84 and publishes
first time. `gpt-4o-mini` climbs 0.50, 0.63, 0.66 and never reaches 0.75, so the
run ends needing a human. The dropdown on the page switches between them. Nothing
about the gate changed; the drafts were genuinely different.

**The loop stops when it stalls.** If a rewrite does not move the draft closer to
passing, the run ends rather than paying for another lap. See
`distance_from_passing` in `pipeline.py`.

## Files

```
app.py        FastAPI, streams each stage to the page as it finishes
pipeline.py   the gate, the three agents, the judge, the thresholds
tools.py      the web search tool, and the collector that keeps the sources
```
