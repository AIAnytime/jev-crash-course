# 04 - Jev vs a language model vs an agent

Three lanes answer the same four questions about the same app-store reviews, at
the same moment: the decision model, a language model with strict structured
output, and an agent that can call a tool before it answers. Every row is a live
API call. The reviewer's star rating is held back and used as the answer key, so
the calibration numbers are measured rather than claimed.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 04-jev-vs-llm-vs-agents
uvicorn app:app --port 8004 --reload
```

Open http://localhost:8004, and http://localhost:8004/whiteboard.html for the
boards.

The older Streamlit front end still works against the same engine:

```bash
streamlit run streamlit_app.py
```

## What is in here

```
app.py                    FastAPI server: race stream, calibration, the pattern demo
streamlit_app.py          the original Streamlit front end, same engine
jevkit/providers/jev.py   one call, four questions
jevkit/providers/gpt.py   the language-model lane, strict JSON schema
jevkit/providers/agent.py the agent lane: tool available, loop until it answers
jevkit/runner.py          concurrent execution with a live event stream
jevkit/metrics.py         calibration error, Brier score, reliability bins
data/reviews.jsonl        1,000 cached app-store reviews
scripts/fetch_reviews.py  rebuilds that file
static/                   the web UI and the whiteboard
```

## The four questions

| Question | Type |
|---|---|
| What is the reviewer's overall sentiment? | pick one |
| What is the review mainly about? | pick one |
| Does it report a concrete defect? | yes/no |
| How likely is this reviewer to leave? | score |

## Reading the numbers

- Wall clock and cost are measured per lane over the same rows, at the same
  concurrency. Change the concurrency and both move; that is the point of having
  the control on screen.
- Calibration needs volume. At 20 rows the error bars swamp the result. Run 300
  rows or more before quoting an ECE number on camera.
- Prices for the language-model lanes are list prices in `jevkit/pricing.py`.
  Check them against current pricing before you record.
