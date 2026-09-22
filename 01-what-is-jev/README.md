# 01 - A model that only makes decisions

A message goes in. Three fixed questions get answered as numbers. Nothing is
written back. The same three questions are then put to a normal language model
so you can see the difference in the clock and in the shape of the answer.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 01-what-is-jev
uvicorn app:app --port 8001 --reload
```

Open http://localhost:8001 for the demo and
http://localhost:8001/whiteboard.html for the boards.

Needs `JEV_API_KEY` in the repo-root `.env`. The language-model side also needs
`OPENAI_API_KEY`; everything else works without it.

## Files

```
app.py              FastAPI server, three questions, two providers
static/index.html   the demo page
static/app.js       page logic
static/boards.json  whiteboard content
```

## The three questions

| Question | Type | Answers |
|---|---|---|
| Does this need a reply from a person? | yes/no | a probability |
| What mood is the writer in? | pick one | happy, neutral, upset |
| How soon does it need attention? | score | four levels, no rush to blocked |
