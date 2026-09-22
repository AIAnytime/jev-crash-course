# 07 - A first pass over a contract

Paste an agreement and pick which side you are on. Every clause is read against
the same five questions, and the document as a whole is checked against ten
protections that ought to be in it. The result is a reading order and a list of
gaps.

This is triage, not legal advice. The point is that a person reads the worst
clause first instead of last.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 07-contract-review
uvicorn app:app --port 8007 --reload
```

Open http://localhost:8007, and http://localhost:8007/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## What it asks

Per clause: what the clause is about, which side it favours, how risky it is on
a four-level scale, whether it is unusual, and whether it would have to be
changed before signing.

Over the whole document: ten yes-or-no questions about protections that should
be present, including a liability cap, whether that cap is mutual, notice
periods, price-increase limits, uptime commitments, data ownership and deletion,
IP indemnity, and assignment on a change of control.

## Files

```
app.py              clause splitting, the two passes, the scoring
data/contracts.py   two sample agreements, one hostile and one reasonable
static/             the demo page and the whiteboard
```

Both samples are invented for the demo. Neither is a real agreement.
