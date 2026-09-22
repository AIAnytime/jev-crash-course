# 03 - Six questions about a piece of text, in one trip

Paste any user-written text. One call answers six questions about it: feeling,
intent, language, whether it contains personal information, whether it is
abusive, and how formal it is. There is a button that times one question against
six on the same text, and a batch mode that runs a list of lines in parallel.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 03-text-analysis
uvicorn app:app --port 8003 --reload
```

Open http://localhost:8003, and http://localhost:8003/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## Files

```
app.py              six questions, the one-vs-six timer, the batch runner
static/index.html   the demo page
static/app.js       page logic
static/boards.json  whiteboard content
```

## Notes

- The first call after the server starts is slower than the rest; the connection
  is being set up. Click once before recording.
- Batch runs with 20 calls in flight. Raise the semaphore in `app.py` if you want
  to push it.
