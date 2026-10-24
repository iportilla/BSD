import os
import math
from typing import List, Tuple

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Autocomplete Demo with Probability‑Colored Suggestions
# ======================================================================


# Fix: Buttons were showing as raw HTML due to quote collisions in `onclick` and
# Markdown sanitization. This version renders the suggestion panel via
# `st.components.v1.html(...)`, attaches click handlers in a `<script>`, and
# uses `window.parent.document` to reach the Streamlit input outside the iframe.
# No inline `onclick` attributes, so no quoting headaches.

# ---------------------------------------------------------------------------
# 1) Configuration
# ---------------------------------------------------------------------------

def get_api_key():
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("OPENAI_API_KEY")
    except Exception:  # no secrets.toml present
        return None


OPENAI_API_KEY = get_api_key()
if not OPENAI_API_KEY:
    st.error("No API key found. Set OPENAI_API_KEY in your environment or st.secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)  # v1 client
DEFAULT_MODEL = "gpt-4o-mini"  # supports logprobs via Chat Completions API

# ---------------------------------------------------------------------------
# 2) Helpers
# ---------------------------------------------------------------------------

def softmax(logits: List[float]) -> List[float]:
    if not logits:
        return []
    m = max(logits)
    exps = [math.exp(x - m) for x in logits]
    total = sum(exps) or 1.0
    return [e / total for e in exps]


def color_from_prob(p: float) -> str:
    if p > 0.70:
        return "rgb(16, 185, 129)"   # green
    if p > 0.40:
        return "rgb(245, 158, 11)"  # amber
    return "rgb(220, 38, 38)"       # red


@st.cache_data(ttl=15)
def fetch_next_tokens(prompt: str, model: str, n: int, temperature: float) -> List[Tuple[str, float]]:
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Continue the user's text. Reply with only the next word or word fragment, "
                               "including a leading space if one belongs between the words.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=1,
            logprobs=True,
            top_logprobs=min(20, max(1, n)),
            temperature=temperature,
        )
    except Exception as e:
        st.warning(f"OpenAI request failed: {e}")
        return []

    try:
        top = resp.choices[0].logprobs.content[0].top_logprobs
        logprob_dict = {t.token: t.logprob for t in top}
    except Exception:
        return []

    if not logprob_dict:
        return []

    tokens, logits = zip(*logprob_dict.items())
    probs = softmax(list(logits))
    pairs = list(zip(tokens, probs))
    pairs.sort(key=lambda t: t[1], reverse=True)
    return pairs[:n]


def visible_label(token: str, prob: float) -> str:
    disp = "␠" if token == " " else token.replace("\n", "⏎").replace("\t", "⇥")
    return f"{disp} — {prob*100:5.2f}%"

# ---------------------------------------------------------------------------
# 3) UI
# ---------------------------------------------------------------------------

st.title("OpenAI Autocomplete Demo")

with st.sidebar:
    st.header("Settings")
    model = st.text_input("Model", value=DEFAULT_MODEL)
    top_n = st.slider("Top‑N suggestions", 1, 10, 5)
    temperature = st.slider("Temperature", 0.0, 1.0, 0.0, step=0.05)
    min_chars = st.slider("Min characters before querying", 0, 20, 3)

if "prompt" not in st.session_state:
    st.session_state.prompt = ""

user_text = st.text_input("Start typing…", key="prompt", label_visibility="visible")

suggestions: List[Tuple[str, float]] = []
if user_text.strip() and len(user_text) >= min_chars:
    suggestions = fetch_next_tokens(user_text, model, top_n, temperature)

def append_token(token: str):
    prompt = st.session_state.prompt
    if prompt and not prompt[-1].isspace() and not token[0].isspace():
        token = " " + token
    st.session_state.prompt += token


def clear_prompt():
    st.session_state.prompt = ""


shown = [(tok, prob) for tok, prob in suggestions if tok.strip()]
if shown:
    st.subheader("Pick the next token")
    for i, (tok, prob) in enumerate(shown):
        swatch = {"rgb(16, 185, 129)": "🟢", "rgb(245, 158, 11)": "🟡"}.get(color_from_prob(prob), "🔴")
        st.button(
            f"{swatch} {visible_label(tok, prob)}",
            key=f"sug-{i}",
            on_click=append_token,
            args=(tok,),
            use_container_width=True,
        )
    st.button("Clear prompt", on_click=clear_prompt)
