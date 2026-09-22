"""Tab 3 -- Calibration. The claim RLCD actually makes, checked against labels.

Ground truth is the reviewer's own star rating, which neither model is shown.
A well-calibrated model that says "0.9" is right about 90% of the time, so its
curve hugs the diagonal.
"""

from __future__ import annotations

import asyncio

import altair as alt
import pandas as pd
import streamlit as st

from jevkit import data
from jevkit.metrics import accuracy, brier, ece, reliability
from jevkit.runner import race

BLURB = """
Every point below is a sentiment call with a stated confidence. We bucket by
confidence and ask: **in this bucket, how often was the answer actually right?**

Perfect calibration is the diagonal. Above it the model is underconfident;
below it -- the usual failure -- it is overconfident, and any threshold you
write in code is built on sand.
"""


def _pairs(tally, rows_by_id) -> list[tuple[float, bool]]:
    out = []
    for r in tally.results:
        if not r.ok:
            continue
        a = r.answers.get("sentiment")
        if a is None or a.value is None:
            continue
        out.append((float(a.confidence), a.value == rows_by_id[r.row_id]["true_sentiment"]))
    return out


def render(providers: list, settings: dict) -> None:
    st.subheader("Calibration")
    st.markdown(BLURB)

    usable = [p for p in providers if p.available]
    if not usable:
        st.error("No provider has a key.")
        return
    if len(usable) < 2:
        st.warning(f"Only {usable[0].label} has a key -- you'll get one curve, not a comparison.")

    c1, c2, c3 = st.columns([2, 1, 1])
    n = c1.slider("reviews", 50, 1000, 300, step=50, key="cal_n")
    concurrency = c2.number_input("concurrency", 1, 200, settings.get("concurrency", 20),
                                  key="cal_concurrency")
    n_bins = c3.number_input("bins", 5, 20, 10, key="cal_bins")

    if st.button("Measure calibration", type="primary", width="stretch", key="cal_go"):
        rows = data.sample(int(n), seed=13)
        rows_by_id = {r["id"]: r for r in rows}
        bar = st.progress(0.0, text="running...")

        def paint(tallies, elapsed):
            done = sum(t.done for t in tallies.values())
            bar.progress(min(done / (n * len(usable)), 1.0),
                         text=f"{done}/{n * len(usable)} decisions -- {elapsed:.1f}s")

        tallies = asyncio.run(race(usable, rows, int(concurrency), paint))
        bar.empty()
        st.session_state["calib"] = {"tallies": tallies, "providers": usable,
                                     "rows_by_id": rows_by_id, "bins": int(n_bins)}

    saved = st.session_state.get("calib")
    if not saved:
        return

    curves, summary = [], []
    for p in saved["providers"]:
        pairs = _pairs(saved["tallies"][p.name], saved["rows_by_id"])
        if not pairs:
            continue
        for b in reliability(pairs, saved["bins"]):
            if b.n:
                curves.append({"provider": p.label, "confidence": b.mean_confidence,
                               "accuracy": b.accuracy, "n": b.n})
        summary.append({"provider": p.label, "n": len(pairs),
                        "accuracy": round(accuracy(pairs), 3),
                        "ECE": round(ece(pairs, saved["bins"]), 4),
                        "Brier": round(brier(pairs), 4),
                        "mean confidence": round(sum(c for c, _ in pairs) / len(pairs), 3)})

    if not summary:
        st.error("No usable answers came back.")
        return

    df = pd.DataFrame(curves)
    diagonal = alt.Chart(pd.DataFrame({"x": [0, 1], "y": [0, 1]})).mark_line(
        strokeDash=[6, 4], color="gray").encode(x="x:Q", y="y:Q")
    line = alt.Chart(df).mark_line(point=True).encode(
        x=alt.X("confidence:Q", title="stated confidence", scale=alt.Scale(domain=[0, 1])),
        y=alt.Y("accuracy:Q", title="actual accuracy", scale=alt.Scale(domain=[0, 1])),
        color=alt.Color("provider:N", title=None),
        size=alt.Size("n:Q", legend=None, scale=alt.Scale(range=[30, 400])),
        tooltip=["provider", "confidence", "accuracy", "n"],
    )
    st.altair_chart((diagonal + line).properties(height=420), width="stretch")

    st.dataframe(pd.DataFrame(summary), width="stretch", hide_index=True)
    st.caption("ECE is mean |confidence − accuracy|, population-weighted. Lower is better.")

    best = min(summary, key=lambda s: s["ECE"])
    if len(summary) > 1:
        worst = max(summary, key=lambda s: s["ECE"])
        st.success(
            f"**{best['provider']}** is the better-calibrated of the two "
            f"(ECE {best['ECE']} vs {worst['ECE']}) -- its confidence means "
            f"something you can branch on."
        )
