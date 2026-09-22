#!/usr/bin/env python3
"""Rebuild data/reviews.jsonl from the public sealuzh/app_reviews corpus
(real Google Play reviews, with the star rating kept as ground truth)."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

OUT = Path(__file__).resolve().parent.parent / "data" / "reviews.jsonl"
API = "https://datasets-server.huggingface.co/rows"
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1000


def main() -> None:
    rows: list[dict] = []
    seen: set[str] = set()
    OUT.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=30) as client:
        for offset in range(0, TARGET * 4, 100):
            try:
                payload = client.get(API, params={
                    "dataset": "sealuzh/app_reviews", "config": "default",
                    "split": "train", "offset": offset, "length": 100,
                }).json()
            except Exception as exc:
                print(f"  skipped offset {offset}: {type(exc).__name__}")
                continue
            for item in payload.get("rows", []):
                r = item["row"]
                text = " ".join((r.get("review") or "").split())
                if len(text) < 40 or text.lower() in seen:
                    continue
                seen.add(text.lower())
                rows.append({"id": len(rows), "app": r["package_name"],
                             "text": text, "stars": r["star"], "date": r.get("date")})
            if len(rows) >= TARGET:
                break
            time.sleep(0.1)

    rows = rows[:TARGET]
    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"wrote {len(rows)} reviews -> {OUT}")
    print("stars:", sorted(Counter(r["stars"] for r in rows).items()))


if __name__ == "__main__":
    main()
