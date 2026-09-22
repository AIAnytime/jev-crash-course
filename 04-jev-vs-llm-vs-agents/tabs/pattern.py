"""Tab 4 -- The Pattern. LLM proposes, Jev decides, code executes.

The LLM does what it is good at (open-ended generation of candidate actions).
Jev does what it is good at (picking one, with a number attached). The gate is
ordinary Python: above the threshold it runs, below it a human looks.
"""

from __future__ import annotations

import asyncio
import json
import os

import pandas as pd
import streamlit as st

from jevkit.config import OPENAI_KEY
from jevkit.providers.jev import JevProvider
from jevkit.schema import QSpec

PROPOSE_SYSTEM = (
    "You triage inbound messages for a mobile app team. Propose 3 to 5 distinct, "
    "concrete actions that could reasonably be taken. Do not choose between them. "
    "Return JSON: {\"actions\":[{\"id\":\"snake_case\",\"description\":\"one line\"}]}"
)

SAMPLES = [
    "The app crashes every single time I try to upload a photo over 5MB. Pixel 8, "
    "latest version. This has been broken for three weeks and support hasn't replied.",
    "Love the new dark mode! Any chance of a widget for the home screen?",
    "I was charged twice for the annual plan this morning and I need the duplicate "
    "refunded today before it hits my overdraft.",
]


async def _propose(ticket: str, model: str) -> list[dict]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ[OPENAI_KEY])
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": PROPOSE_SYSTEM},
                      {"role": "user", "content": ticket}],
            response_format={"type": "json_object"},
        )
        payload = json.loads(resp.choices[0].message.content)
    finally:
        await client.close()
    actions = payload.get("actions", [])
    return [a for a in actions if a.get("id") and a.get("description")][:5]


async def _decide(actions: list[dict], ticket: str):
    specs = [
        QSpec(key="action", kind="choice",
              instructions="Which single action best resolves this message?",
              options={a["id"]: a["description"] for a in actions}),
        QSpec(key="is_urgent", kind="noul",
              instructions="Does this message communicate genuine time pressure?"),
    ]
    provider = JevProvider(specs=specs)
    try:
        return await provider.decide({"id": 0, "app": "inbox", "text": ticket})
    finally:
        await provider.aclose()


def render(providers: list, settings: dict) -> None:
    st.subheader("The Pattern")
    st.caption("code calculates · Jev judges · LLMs reason and create")

    jev = next((p for p in providers if p.name == "jev"), None)
    gpt = next((p for p in providers if p.name == "gpt"), None)

    preset = st.selectbox("example", range(len(SAMPLES)),
                          format_func=lambda i: SAMPLES[i][:70] + "...", key="pat_example")
    ticket = st.text_area("incoming message", SAMPLES[preset], height=120, key="pat_ticket")
    threshold = st.slider("auto-execute above confidence", 0.5, 0.99, 0.85, 0.01,
                          key="pat_threshold")

    if not st.button("Route it", type="primary", width="stretch", key="pat_go"):
        return
    if not (gpt and gpt.available):
        st.error("Needs OPENAI_API_KEY to propose actions.")
        return

    with st.spinner("LLM proposing candidate actions..."):
        actions = asyncio.run(_propose(ticket, gpt.model))
    if not actions:
        st.error("The LLM proposed nothing usable.")
        return

    st.markdown("##### 1. LLM proposes")
    for a in actions:
        st.markdown(f"- `{a['id']}` -- {a['description']}")

    if not (jev and jev.available):
        st.warning("Needs TYPESAFE_API_KEY for the decision step. "
                   "The proposal half of the pattern is shown above.")
        return

    st.markdown("##### 2. Jev decides")
    with st.spinner("deciding..."):
        result = asyncio.run(_decide(actions, ticket))
    if not result.ok:
        st.error(result.error)
        return

    action = result.answers["action"]
    urgent = result.answers.get("is_urgent")

    probs = pd.DataFrame(
        sorted((action.probabilities or {}).items(), key=lambda kv: -kv[1]),
        columns=["action", "probability"],
    )
    st.bar_chart(probs, x="action", y="probability", horizontal=True)
    a, b, c = st.columns(3)
    a.metric("action", action.value)
    b.metric("confidence", f"{action.confidence:.1%}")
    if urgent is not None:
        c.metric("urgent", f"{urgent.raw_noul:.1%}")
    st.caption(f"decided in {result.latency_s * 1000:.0f}ms")

    st.markdown("##### 3. Code executes")
    if action.confidence >= threshold:
        st.success(f"confidence {action.confidence:.2f} >= {threshold:.2f} -- "
                   f"executing `{action.value}` automatically.")
    else:
        st.warning(f"confidence {action.confidence:.2f} < {threshold:.2f} -- "
                   f"escalating to a human. Nothing was executed.")
    st.code(
        f"""answer = client.system_one(state=ticket, questions=questions).answers["action"]

if answer.confidence >= {threshold:.2f}:
    execute(answer.choice)          # -> {action.value}
else:
    escalate_to_human(ticket)""",
        language="python",
    )
