# 05 - A tool that measures writing instead of rewriting it

Type on the left, scores appear on the right: clarity, warmth, hype,
concreteness, reader effort, plus two yes-or-no calls. It updates while you
type, because a measurement that takes a few hundred milliseconds can afford to
run on every pause. There is also a side-by-side mode for comparing two drafts.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 05-text-measure
uvicorn app:app --port 8005 --reload
```

Open http://localhost:8005, and http://localhost:8005/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## Files

```
app.py              seven questions and two endpoints
static/index.html   the demo page
static/app.js       debounced live measuring, and the A/B table
static/boards.json  whiteboard content
```

## Changing what it measures

Every dial is an entry in `QUESTIONS` in `app.py`. A score is a list of four
descriptions from worst to best; a yes-or-no is one sentence. Add an entry, add
a label in `LABELS`, reload. Extra questions ride along on the same call, so an
eighth dial costs almost nothing in time.
