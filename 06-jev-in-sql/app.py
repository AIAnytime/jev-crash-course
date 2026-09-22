"""Video 6 - calling Jev from SQL and reviewing a thousand rows in one query.

    uvicorn app:app --port 8006 --reload

DuckDB holds the reviews. The jev_* functions in jevsql.py are registered as
column-at-a-time functions, so the query engine hands them the whole column and
they answer it concurrently.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import duckdb
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import jevsql

HERE = Path(__file__).resolve().parent
REVIEWS = HERE / "data" / "reviews.jsonl"

PRESETS = [
    {
        "name": "How do people feel, overall",
        "sql": "SELECT jev_sentiment(text) AS feeling,\n"
               "       count(*) AS reviews\n"
               "FROM reviews\n"
               "GROUP BY 1\n"
               "ORDER BY reviews DESC",
    },
    {
        "name": "Real bugs, worst first",
        "sql": "SELECT round(jev_is_bug(text), 2) AS bug_chance,\n"
               "       stars,\n"
               "       text\n"
               "FROM reviews\n"
               "WHERE jev_is_bug(text) > 0.8\n"
               "ORDER BY bug_chance DESC\n"
               "LIMIT 25",
    },
    {
        "name": "Which app is losing people",
        "sql": "SELECT app,\n"
               "       count(*) AS reviews,\n"
               "       round(avg(jev_churn_risk(text)), 2) AS avg_churn_risk\n"
               "FROM reviews\n"
               "GROUP BY app\n"
               "HAVING count(*) > 20\n"
               "ORDER BY avg_churn_risk DESC",
    },
    {
        "name": "What people complain about",
        "sql": "SELECT jev_topic(text) AS topic,\n"
               "       count(*) AS reviews,\n"
               "       round(avg(stars), 2) AS avg_stars\n"
               "FROM reviews\n"
               "WHERE jev_sentiment(text) = 'negative'\n"
               "GROUP BY topic\n"
               "ORDER BY reviews DESC",
    },
    {
        "name": "Where the stars and the words disagree",
        "sql": "SELECT stars,\n"
               "       jev_sentiment(text) AS feeling,\n"
               "       round(jev_sentiment_confidence(text), 2) AS sure,\n"
               "       text\n"
               "FROM reviews\n"
               "WHERE (stars >= 4 AND jev_sentiment(text) = 'negative')\n"
               "   OR (stars <= 2 AND jev_sentiment(text) = 'positive')\n"
               "ORDER BY sure DESC\n"
               "LIMIT 25",
    },
]

FUNCTIONS = [
    ("jev_sentiment(text)", "VARCHAR", "positive, neutral or negative"),
    ("jev_sentiment_confidence(text)", "DOUBLE", "how sure that feeling is, 0 to 1"),
    ("jev_topic(text)", "VARCHAR", "performance, ui, features, pricing, bugs, other"),
    ("jev_is_bug(text)", "DOUBLE", "probability this is a real defect"),
    ("jev_churn_risk(text)", "DOUBLE", "0 (committed) to 4 (gone)"),
]

app = FastAPI(title="Jev in SQL")

connection = duckdb.connect(":memory:")
connection.execute(
    "CREATE TABLE all_reviews AS "
    f"SELECT id, app, text, stars, date FROM read_json_auto('{REVIEWS}')"
)
jevsql.register(connection)


class Query(BaseModel):
    sql: str
    limit: int = 200


READ_ONLY = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)


@app.get("/api/presets")
def presets() -> dict:
    total = connection.execute("SELECT count(*) FROM all_reviews").fetchone()[0]
    return {
        "presets": PRESETS,
        "functions": [
            {"signature": s, "returns": r, "meaning": m} for s, r, m in FUNCTIONS
        ],
        "rows_available": total,
        "cached": jevsql.cache_size(),
        "concurrency": jevsql.CONCURRENCY,
    }


@app.get("/api/progress")
def progress() -> dict:
    snap = jevsql.stats.snapshot()
    snap["cache_size"] = jevsql.cache_size()
    return snap


@app.post("/api/cache/clear")
def clear() -> dict:
    jevsql.clear_cache()
    return {"cached": 0}


@app.post("/api/query")
def query(body: Query) -> JSONResponse:
    sql = body.sql.strip().rstrip(";")
    if not READ_ONLY.match(sql):
        return JSONResponse({"error": "Only SELECT and WITH queries run here."},
                            status_code=400)

    jevsql.stats.reset()
    rows_in_play = max(1, min(body.limit, 1000))
    connection.execute(
        "CREATE OR REPLACE VIEW reviews AS "
        f"SELECT * FROM all_reviews ORDER BY id LIMIT {rows_in_play}"
    )

    started = time.perf_counter()
    try:
        result = connection.execute(sql)
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
    except Exception as exc:
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=400)
    elapsed = time.perf_counter() - started

    snap = jevsql.stats.snapshot()
    return JSONResponse({
        "columns": columns,
        "rows": [[_safe(v) for v in row] for row in rows[:500]],
        "row_count": len(rows),
        "seconds": elapsed,
        "scanned": rows_in_play,
        "calls": snap["calls"],
        "cached": snap["cached"],
        "errors": snap["errors"],
        "cost": snap["cost"],
        "cache_size": jevsql.cache_size(),
    })


def _safe(value):
    if isinstance(value, (int, float, str)) or value is None:
        return value
    return str(value)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
