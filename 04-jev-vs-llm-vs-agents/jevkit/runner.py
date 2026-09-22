"""Concurrent execution with a live event stream, so the UI can fill in
as results land instead of blocking until the whole run finishes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from .providers.base import Result


@dataclass
class Tally:
    """Running totals for one provider."""
    label: str
    done: int = 0
    errors: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_s: float = 0.0
    latencies: list[float] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    finished: bool = False

    def add(self, r: Result, elapsed: float) -> None:
        self.done += 1
        self.wall_s = elapsed
        self.results.append(r)
        if r.ok:
            self.input_tokens += r.input_tokens
            self.output_tokens += r.output_tokens
            self.latencies.append(r.latency_s)
        else:
            self.errors += 1

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0.0
        s = sorted(self.latencies)
        return s[len(s) // 2]

    @property
    def rows_per_s(self) -> float:
        return self.done / self.wall_s if self.wall_s > 0 else 0.0


async def _drive(provider, rows, queue: asyncio.Queue, concurrency: int, t0: float):
    sem = asyncio.Semaphore(concurrency)

    async def one(row):
        async with sem:
            result = await provider.decide(row)
            await queue.put(("result", provider.name, result, time.perf_counter() - t0))

    try:
        await asyncio.gather(*(one(r) for r in rows))
    finally:
        await queue.put(("done", provider.name, None, time.perf_counter() - t0))


async def race(providers, rows, concurrency: int, on_event, tick_s: float = 0.12):
    """Run every provider over `rows` at once, calling on_event(tallies) as
    results arrive. Returns the final tallies keyed by provider name."""
    tallies = {p.name: Tally(label=p.label) for p in providers}
    queue: asyncio.Queue = asyncio.Queue()
    t0 = time.perf_counter()

    tasks = [asyncio.create_task(_drive(p, rows, queue, concurrency, t0)) for p in providers]
    remaining = len(providers)

    try:
        await _consume(queue, tallies, remaining, on_event, tick_s, t0)
        await asyncio.gather(*tasks)
    finally:
        # Clients must be closed on the loop that created them; Streamlit spins
        # up a fresh loop per rerun, so leaving them open leaks connections.
        for p in providers:
            await p.aclose()
    on_event(tallies, time.perf_counter() - t0)
    return tallies


async def _consume(queue, tallies, remaining, on_event, tick_s, t0):
    last_paint = 0.0
    while remaining:
        kind, name, result, elapsed = await queue.get()
        if kind == "done":
            tallies[name].finished = True
            remaining -= 1
            on_event(tallies, time.perf_counter() - t0)
            last_paint = time.perf_counter()
            continue

        tallies[name].add(result, elapsed)
        # Repaint on a timer; painting every row would dominate the wall clock.
        now = time.perf_counter()
        if now - last_paint >= tick_s:
            on_event(tallies, now - t0)
            last_paint = now
