"""jev-toolkit -- see what a System One model actually buys you.

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import streamlit as st

from jevkit.config import (OPENAI_KEY, TYPESAFE_KEY, has_key, load_env,
                           resolve_typesafe_key)
from jevkit.pricing import DEFAULT_OPENAI_MODEL, OPENAI_PRICES, Price
from jevkit.providers.gpt import GPTProvider
from jevkit.providers.jev import JevProvider
from tabs import calibration, pattern, race, why

load_env()

st.set_page_config(page_title="jev-toolkit", page_icon="⚡", layout="wide")


def sidebar() -> tuple[list, dict]:
    with st.sidebar:
        st.title("jev-toolkit")
        st.caption("Jev vs an LLM, on the same real reviews.")

        st.subheader("Keys")
        found_as = resolve_typesafe_key()
        if found_as:
            st.success(f"Jev — {found_as} found")
        else:
            st.error(f"Jev — {TYPESAFE_KEY} missing")
        if has_key(OPENAI_KEY):
            st.success(f"OpenAI — {OPENAI_KEY} found")
        else:
            st.error(f"OpenAI — {OPENAI_KEY} missing")
        if not has_key(TYPESAFE_KEY):
            st.caption(
                "Get a key at console.typesafe.ai/settings/keys, add "
                "`TYPESAFE_API_KEY=...` to `.env`, and reload. Everything that "
                "does not need Jev still runs without it."
            )

        st.subheader("Baseline")
        model = st.selectbox("OpenAI model", list(OPENAI_PRICES),
                             index=list(OPENAI_PRICES).index(DEFAULT_OPENAI_MODEL),
                             key="sb_model")
        default = OPENAI_PRICES[model]
        with st.expander("pricing ($ / 1M tokens)"):
            st.caption("Defaults may be stale — check OpenAI's current pricing.")
            pin = st.number_input("input", 0.0, 100.0, default.input_per_mtok, 0.01,
                                  format="%.3f", key="sb_price_in")
            pout = st.number_input("output", 0.0, 100.0, default.output_per_mtok, 0.01,
                                   format="%.3f", key="sb_price_out")
            st.caption("Jev: $0.042 in / $0.00 out (published).")

        st.subheader("Run")
        concurrency = st.slider("concurrency", 1, 100, 20, key="sb_concurrency",
                                help="In-flight requests per provider.")
        jev_model = st.text_input("Jev model", "jev-latest", key="sb_jev_model")

    providers = [
        JevProvider(model=jev_model),
        GPTProvider(model=model, price=Price(pin, pout)),
    ]
    return providers, {"concurrency": concurrency, "n": 100}


def main() -> None:
    providers, settings = sidebar()
    st.title("⚡ jev-toolkit")

    t1, t2, t3, t4 = st.tabs(
        ["🏁 The Race", "🧠 Why It's Fast", "🎯 Calibration", "🔀 The Pattern"]
    )
    with t1:
        race.render(providers, settings)
    with t2:
        why.render(providers, settings)
    with t3:
        calibration.render(providers, settings)
    with t4:
        pattern.render(providers, settings)


if __name__ == "__main__":
    main()
