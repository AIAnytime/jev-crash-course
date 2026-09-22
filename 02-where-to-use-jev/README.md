# 02 - Which jobs belong to a decision model

Type a job your software has to do. Jev sorts it into plain code, Jev, or a
language model, and shows why. The built-in list of twelve jobs runs as twelve
parallel calls so the whole picture arrives in about a second.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 02-where-to-use-jev
uvicorn app:app --port 8002 --reload
```

Open http://localhost:8002, and http://localhost:8002/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## Files

```
app.py              the four questions and the batch runner
static/index.html   the demo page
static/app.js       page logic
static/boards.json  whiteboard content
```

## The questions it asks about your job

- Who should own this: code, Jev, or a language model
- Could every acceptable answer be listed in advance
- Does the job have to produce prose
- How much step-by-step reasoning it needs
