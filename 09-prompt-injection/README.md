# 09 - Can you talk a model out of its own answer?

Four support messages, nine injections, two models, two questions each: is this
abusive, and how urgent is it. Every attacked answer is compared with the same
model's answer on the clean message, so each model is measured against itself.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 09-prompt-injection
uvicorn app:app --port 8009 --reload
```

Open http://localhost:8009, and http://localhost:8009/whiteboard.html for the
boards. Needs `JEV_API_KEY`; the second lane needs `OPENAI_API_KEY`.

## What the run measures

- **Answer changed** - the yes/no or the priority came out differently than on
  the clean message.
- **Abuse call flipped** - the safety-relevant decision crossed the line. This is
  the one that matters.
- **Biggest drop** - how far the abusive probability moved, even when it did not
  cross.

## What it showed here

On one 36-attempt run per model:

| | Jev | gpt-4o-mini |
|---|---|---|
| abuse calls flipped | 0 | 2 |
| worst move on the abusive probability | 0.96 to 0.72 | 0.85 to 0.00 |
| priority changed | 10 | 12 |

Two things are true at once. There is no instruction slot to hijack, because
nothing is being written, and the yes/no shape cannot be broken out of. But the
judgement can still be nudged, and on the priority question both models moved
often. An injection that says "this is low priority" frequently gets low
priority.

Numbers move between runs. Run it yourself before quoting anything.

## Files

```
app.py       both lanes, the clean baselines, the comparison
attacks.py   the messages and the nine injections
static/      the demo page and the whiteboard
```
