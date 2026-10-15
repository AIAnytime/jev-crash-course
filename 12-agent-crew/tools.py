"""The one tool the crew gets: web search.

Results are also kept in a collector, because two things later need to see what
was actually found. The page shows the sources, and Jev is asked whether the
draft stuck to them.
"""

from __future__ import annotations

import threading
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

import jevlib


class Collector:
    """Somewhere for the tool to put what it found, since the agent only ever
    returns prose."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.results: list[dict] = []
        self.queries: list[str] = []

    def add(self, query: str, results: list[dict]) -> None:
        with self.lock:
            self.queries.append(query)
            for r in results:
                if not any(existing["url"] == r["url"] for existing in self.results):
                    self.results.append(r)

    def as_notes(self) -> str:
        with self.lock:
            if not self.results:
                return "No sources were retrieved."
            return "\n\n".join(
                f"[{i + 1}] {r['title']}\n{r['url']}\n{r['content'][:600]}"
                for i, r in enumerate(self.results)
            )

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "queries": list(self.queries),
                "sources": [
                    {"title": r["title"], "url": r["url"], "score": r.get("score")}
                    for r in self.results
                ],
            }


class SearchInput(BaseModel):
    query: str = Field(..., description="What to search the web for.")


class WebSearch(BaseTool):
    name: str = "web_search"
    description: str = (
        "Search the web for current information. Give it a short, specific query. "
        "Returns titles, urls and extracts from the top results."
    )
    args_schema: Type[BaseModel] = SearchInput
    collector: Collector = None  # type: ignore[assignment]
    max_results: int = 5

    def _run(self, query: str) -> str:
        key = tavily_key()
        if not key:
            return (
                "Web search is unavailable because no TAVILY_API_KEY is set. "
                "Answer from what you already know, and do not invent citations."
            )
        from tavily import TavilyClient

        try:
            response = TavilyClient(api_key=key).search(
                query=query, max_results=self.max_results, search_depth="basic"
            )
        except Exception as exc:
            return f"Search failed: {type(exc).__name__}: {exc}"

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "score": r.get("score"),
            }
            for r in response.get("results", [])
        ]
        if self.collector is not None:
            self.collector.add(query, results)
        if not results:
            return f"No results for {query!r}."
        return "\n\n".join(
            f"[{i + 1}] {r['title']}\n{r['url']}\n{r['content'][:700]}"
            for i, r in enumerate(results)
        )


def tavily_key() -> str | None:
    import os

    jevlib.load_env()
    return os.environ.get("TAVILY_API_KEY", "").strip() or None


def search_available() -> bool:
    return tavily_key() is not None
