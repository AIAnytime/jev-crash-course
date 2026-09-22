"""Tab 1 -- The Race. Both providers over the same reviews, live."""

from __future__ import annotations

import asyncio

import pandas as pd
import streamlit as st

from jevkit import data
from jevkit.runner import Tally, race
from jevkit.schema import REVIEW_QUESTIONS


def _lane(container, tally: Tally, provider, total: int, elapsed: float) -> None:
    cost = provider.cost_usd(tally.input_tokens, tally.output_tokens)
    with container:
        st.progress(min(tally.done / total, 1.0))
        a, b, c = st.columns(3)
        a.metric("rows", f"{tally.done}/{total}")
        b.metric("wall clock", f"{tally.wall_s:.2f}s")
        c.metric("cost", f"${cost:.4f}")
        d, e = st.columns(2)
        d.metric("rows/sec", f"{tally.rows_per_s:.1f}")
        e.metric("p50 latency", f"{tally.p50_latency * 1000:.0f}ms")
        if tally.errors:
            st.caption(f":red[{tally.errors} errored]")


def _results_frame(tally: Tally, rows_by_id: dict) -> pd.DataFrame:
    records = []
    for r in tally.results[-200:]:
        if not r.ok:
            continue
        rec = {"review": rows_by_id[r.row_id]["text"][:80]}
        for q in REVIEW_QUESTIONS:
            a = r.answers.get(q.key)
            if a is None:
                continue
            rec[q.key] = f"{a.value} ({a.confidence:.2f})"
        records.append(rec)
    return pd.DataFrame(records)


def render(providers: list, settings: dict) -> None:
    st.subheader("The Race")
    st.caption(
        "Same reviews, same four questions, same moment. "
        "Watch the wall clock and the cost meter, not the answers."
    )

    usable = [p for p in providers if p.available]
    missing = [p.label for p in providers if not p.available]
    if missing:
        st.warning(f"Not racing (no API key): {', '.join(missing)}")
    if not usable:
        st.error("No provider has a key. Add one to .env and reload.")
        return

    c1, c2, c3 = st.columns([2, 1, 1])
    n = c1.slider("reviews", 10, 1000, settings.get("n", 100), step=10, key="race_n")
    concurrency = c2.number_input("concurrency", 1, 200, settings.get("concurrency", 20),
                                  key="race_concurrency")
    seed = c3.number_input("seed", 0, 9999, 0, key="race_seed")

    if not st.button("Run the race", type="primary", width="stretch", key="race_go"):
        _show_last(usable)
        return

    rows = data.sample(n, seed=seed)
    rows_by_id = {r["id"]: r for r in rows}

    header = st.columns(len(usable))
    lanes = []
    for col, p in zip(header, usable):
        with col:
            st.markdown(f"### {p.label}")
            lanes.append(st.empty())

    clock = st.empty()

    def paint(tallies: dict, elapsed: float) -> None:
        clock.markdown(f"**elapsed {elapsed:.2f}s**")
        for slot, p in zip(lanes, usable):
            slot.empty()
            _lane(slot.container(), tallies[p.name], p, n, elapsed)

    with st.spinner("racing..."):
        tallies = asyncio.run(race(usable, rows, int(concurrency), paint))

    st.session_state["race"] = {
        "tallies": tallies, "providers": usable, "rows_by_id": rows_by_id, "n": n,
    }
    _summary(tallies, usable, rows_by_id, n)


def _show_last(usable: list) -> None:
    last = st.session_state.get("race")
    if last:
        st.info("Showing the previous run.")
        _summary(last["tallies"], last["providers"], last["rows_by_id"], last["n"])


def _summary(tallies: dict, providers: list, rows_by_id: dict, n: int) -> None:
    st.divider()
    summary = []
    for p in providers:
        t = tallies[p.name]
        summary.append({
            "provider": p.label,
            "rows": t.done,
            "wall clock (s)": round(t.wall_s, 2),
            "rows/sec": round(t.rows_per_s, 1),
            "p50 latency (ms)": round(t.p50_latency * 1000),
            "input tokens": t.input_tokens,
            "output tokens": t.output_tokens,
            "cost ($)": round(p.cost_usd(t.input_tokens, t.output_tokens), 5),
            "errors": t.errors,
        })
    df = pd.DataFrame(summary)
    st.dataframe(df, width="stretch", hide_index=True)

    if len(summary) == 2:
        fast, slow = sorted(summary, key=lambda s: s["wall clock (s)"])
        cheap, pricey = sorted(summary, key=lambda s: s["cost ($)"])
        bits = []
        if slow["wall clock (s)"] and fast["wall clock (s)"]:
            bits.append(f"**{fast['provider']} was {slow['wall clock (s)'] / fast['wall clock (s)']:.1f}x faster**")
        if cheap["cost ($)"] > 0:
            bits.append(f"**{pricey['cost ($)'] / cheap['cost ($)']:.0f}x cheaper**")
        elif pricey["cost ($)"] > 0:
            bits.append(f"**{cheap['provider']} cost $0.00 at this volume**")
        if bits:
            st.success(" and ".join(bits) + f" over {n} reviews.")

    for p in providers:
        t = tallies[p.name]
        with st.expander(f"{p.label} -- decisions"):
            st.dataframe(_results_frame(t, rows_by_id), width="stretch",
                         hide_index=True)
        errs = [r.error for r in t.results if not r.ok]
        if errs:
            with st.expander(f"{p.label} -- {len(errs)} errors"):
                st.code("\n".join(sorted(set(errs))[:10]))
