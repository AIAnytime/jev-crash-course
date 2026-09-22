"""Tab 2 -- Why It's Fast. One review, both models, side by side and live.

The left pane streams real tokens as they arrive. The right pane sits blank and
then snaps to a full distribution, because there is nothing to stream: the
readout is a softmax, not a sequence.
"""

from __future__ import annotations

import asyncio
import os
import time

import altair as alt
import pandas as pd
import streamlit as st

from jevkit import data
from jevkit.config import OPENAI_KEY
from jevkit.providers.gpt import SYSTEM, _json_schema, _prompt
from jevkit.schema import REVIEW_QUESTIONS

EXPLAINER = """
**An LLM** must emit its answer as text, one token at a time. Each token needs a
full forward pass, and token *n+1* cannot start until token *n* exists. Four
questions means four times the tokens, serially.

**Jev** encodes the review once into a KV cache, then branches every question off
that shared state in parallel. The last layer is a matmul into a softmax, so the
answer *is* a probability vector -- it never becomes text, so there is nothing to
decode. Four questions cost roughly what one costs.

That is the whole speed story: **prefill once, read out in parallel.**
"""


async def _stream_gpt(row, model, slot, timer):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ[OPENAI_KEY])
    t0 = time.perf_counter()
    buf = ""
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _prompt(REVIEW_QUESTIONS, row)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "review_decisions",
                    "strict": True,
                    "schema": _json_schema(REVIEW_QUESTIONS),
                },
            },
            stream=True,
            stream_options={"include_usage": False},
        )
        async for chunk in stream:
            piece = chunk.choices[0].delta.content or ""
            if not piece:
                continue
            buf += piece
            slot.code(buf[-700:], language="json")
            timer.metric("elapsed", f"{time.perf_counter() - t0:.2f}s")
    except Exception as exc:
        slot.error(f"{type(exc).__name__}: {exc}")
    finally:
        await client.close()
    timer.metric("total", f"{time.perf_counter() - t0:.2f}s")
    return time.perf_counter() - t0


async def _run_jev(provider, row, slot, timer):
    t0 = time.perf_counter()
    slot.caption("prefilling shared state...")
    result = await provider.decide(row)
    elapsed = time.perf_counter() - t0
    if not result.ok:
        slot.error(result.error)
        return elapsed

    frames = []
    for q in REVIEW_QUESTIONS:
        a = result.answers.get(q.key)
        if a is None or not a.probabilities:
            continue
        for label, p in a.probabilities.items():
            frames.append({"question": q.key, "option": str(label), "p": p})
    df = pd.DataFrame(frames)
    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("p:Q", title="probability", scale=alt.Scale(domain=[0, 1])),
            y=alt.Y("option:N", title=None, sort="-x"),
            row=alt.Row("question:N", title=None),
            tooltip=["question", "option", "p"],
        )
        .properties(height=70)
    )
    slot.altair_chart(chart, width="stretch")
    timer.metric("total", f"{elapsed:.2f}s")
    return elapsed


async def _both(jev, row, model, slots):
    try:
        return await asyncio.gather(
            _stream_gpt(row, model, slots["gpt_out"], slots["gpt_timer"]),
            _run_jev(jev, row, slots["jev_out"], slots["jev_timer"]),
        )
    finally:
        await jev.aclose()


def render(providers: list, settings: dict) -> None:
    st.subheader("Why It's Fast")
    st.markdown(EXPLAINER)
    st.divider()

    jev = next((p for p in providers if p.name == "jev"), None)
    gpt = next((p for p in providers if p.name == "gpt"), None)

    rows = data.sample(25, seed=7)
    labels = [f"{r['app'].split('.')[-1]} ({r['stars']}*) -- {r['text'][:60]}..." for r in rows]
    idx = st.selectbox("review", range(len(rows)), format_func=lambda i: labels[i],
                       key="why_row")
    row = rows[idx]
    st.info(row["text"])

    if not st.button("Ask both", type="primary", width="stretch", key="why_go"):
        return
    if not (gpt and gpt.available):
        st.error("Needs OPENAI_API_KEY.")
        return

    left, right = st.columns(2)
    with left:
        st.markdown(f"#### {gpt.label} -- decoding")
        gpt_timer = st.empty()
        gpt_out = st.empty()
    with right:
        st.markdown("#### Jev -- readout")
        jev_timer = st.empty()
        jev_out = st.empty()

    if not (jev and jev.available):
        jev_out.warning("Needs TYPESAFE_API_KEY. Streaming the LLM side only.")
        asyncio.run(_stream_gpt(row, gpt.model, gpt_out, gpt_timer))
        return

    slots = {"gpt_out": gpt_out, "gpt_timer": gpt_timer,
             "jev_out": jev_out, "jev_timer": jev_timer}
    gpt_s, jev_s = asyncio.run(_both(jev, row, gpt.model, slots))
    if jev_s > 0:
        st.success(f"Jev answered all four questions **{gpt_s / jev_s:.0f}x faster** "
                   f"({jev_s * 1000:.0f}ms vs {gpt_s:.2f}s).")
