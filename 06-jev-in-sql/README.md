# 06 - Calling Jev from SQL

A thousand app-store reviews in a local DuckDB database, and five `jev_`
functions you can use anywhere a column goes: in the SELECT list, in WHERE, in
GROUP BY, inside an aggregate. One query reviews the whole table.

## Run

From the repo root:

```bash
source .venv/bin/activate
cd 06-jev-in-sql
uvicorn app:app --port 8006 --reload
```

Open http://localhost:8006, and http://localhost:8006/whiteboard.html for the
boards. Needs `JEV_API_KEY` in the repo-root `.env`.

## The functions

| Function | Returns | Meaning |
|---|---|---|
| `jev_sentiment(text)` | VARCHAR | positive, neutral, negative |
| `jev_sentiment_confidence(text)` | DOUBLE | how sure that feeling is |
| `jev_topic(text)` | VARCHAR | performance, ui, features, pricing, bugs, other |
| `jev_is_bug(text)` | DOUBLE | probability of a real defect |
| `jev_churn_risk(text)` | DOUBLE | 0 committed, 4 gone |

## How it keeps up

The functions are registered as column-at-a-time (Arrow) functions, so DuckDB
hands over the whole column and `jevsql.py` runs 40 calls concurrently against
it. Measured on this machine: 1,000 rows in about 10 seconds, roughly 97 rows a
second, about three cents.

All five functions come from the same underlying call, and results are cached by
review text. A query that uses `jev_sentiment` and `jev_topic` together pays
once, and running the same query again pays nothing. **Empty the cache** before
recording a timing shot.

## Files

```
app.py     FastAPI server, DuckDB connection, the example queries
jevsql.py  the jev_* functions, the concurrency, the cache
data/      1,000 cached reviews
```
