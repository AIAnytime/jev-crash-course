# 08 - Browser tests that read the page

Playwright clicks through a small shop. After every step the page is handed to
Jev with the sentence the test expected to be true, and Jev answers whether it
actually is. There are no selectors in the assertions and no expected strings.

The shop has a switch: run it as the working build or the broken one. In the
broken build the basket total does not update on the first add, and submitting an
empty form shows a stack trace instead of a message.

## Run

From the repo root:

```bash
source .venv/bin/activate
python -m playwright install chromium     # once
cd 08-playwright-testing
uvicorn app:app --port 8008 --reload
```

Open http://localhost:8008. The app under test is at
http://localhost:8008/shop/index.html (add `?bug=1` to break it), and the boards
are at http://localhost:8008/whiteboard.html.

## What is asked after every step

| Question | Used for |
|---|---|
| Is what the test expected actually true of this page? | pass, fail, or not sure |
| What state is this page in? | working, user error, crash, success |
| Would a non-technical person understand the message? | the clarity score |
| Can the customer carry on? | severity |

Pass is 0.8 and above, fail is 0.35 and below, anything between is reported as
not sure rather than being rounded into a green tick.

## Files

```
app.py               the scenarios, the browser driving, the judging
static/shop/         the app under test, with the bug behind ?bug=1
static/index.html    the test runner UI, with screenshots per step
```

## Notes

- The page snapshot includes form field values. Playwright's `inner_text` leaves
  them out, so without that a test that fills a form sees no change at all.
- The expectations are the test. If a step comes back unsure, sharpen the
  sentence rather than lowering the threshold.
