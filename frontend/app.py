"""BundesBot — Streamlit chat interface for German parliamentary data.

Run:
    streamlit run frontend/app.py
"""

# Standard library
import asyncio
import copy
import gc
import html as _html
import json
import logging
import threading
from typing import Any

# Third-party
import streamlit as st

# ── Page config — must be the very first Streamlit call ──────────────────────
st.set_page_config(
    page_title="BundesBot",
    page_icon="🏛️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Local
from dip_mcp.cli.chat import TOOL_SCHEMAS, _dispatch_tool  # noqa: E402
from dip_mcp.config import settings  # noqa: E402
from dip_mcp.llm.groq_client import CHAT_SYSTEM_PROMPT, GroqClient  # noqa: E402

log: logging.Logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
PAGE_TITLE: str = "BundesBot"
GC_TRIGGER_EVERY_N_TURNS: int = 10

HINT_CHIPS: list[str] = [
    "Fraktion split in WP 20?",
    "Who is Friedrich Merz?",
    "How many MdBs in WP 20?",
]

INFO_TEXT: str = """
**BundesBot** reads live German parliamentary (Bundestag) open data and answers
your questions in plain language.

**You can ask about:**
- Fraktion (parliamentary group) distribution across election periods
- Profiles of individual Members of the Bundestag (MdBs)
- Party representation and group membership

**How to use it:**
- Type a question and press **Enter** (or the **↑** button)
- Tap a suggestion below to try an example
- Ask in English or German — answers come back in the language you asked

**Data:** Bundestag Open Data (DIP API)  ·  **Model:** Groq (Llama tool-calling)
"""

# ── Custom CSS ────────────────────────────────────────────────────────────────
# Direction: light "institutional paper" surface with the German federal
# tricolour (Schwarz-Rot-Gold) as the signature device. Brass gold accent,
# oxblood red used sparingly. Bricolage Grotesque display / Inter body /
# Space Mono for data + eyebrow labels.
CUSTOM_CSS: str = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Inter:wght@400;500;600&family=Space+Mono:wght@400;700&display=swap');

:root {
    --paper:      #F1EFE9;
    --surface:    #FBFAF7;
    --ink:        #1C1B19;
    --ink-soft:   #5C5A54;
    --ink-faint:  #908D84;
    --gold:       #B8902B;
    --gold-deep:  #9A7722;
    --red:        #93312B;
    --line:       #DDD9CF;
    --line-soft:  #E7E3DA;
}

/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: var(--paper) !important;
}
.stApp { font-family: 'Inter', system-ui, sans-serif !important; }
.block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 700px !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
    padding-top: 2.2rem !important;
    padding-bottom: 6rem !important;
    margin: 0 auto !important;
}
#MainMenu, footer,
[data-testid="stHeader"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stToolbar"] {
    display: none !important;
}

/* ── Header / wordmark ───────────────────────────────────────────────────── */
.bb-header {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    padding-bottom: 0.4rem;
}
.bb-title {
    font-family: 'Bricolage Grotesque', sans-serif;
    font-size: 2.5rem;
    font-weight: 800;
    color: var(--ink);
    letter-spacing: -1.2px;
    line-height: 1;
    margin: 0;
}
/* The signature: black-red-gold federal rule under the wordmark */
.bb-tricolor {
    display: flex;
    width: 86px;
    height: 4px;
    border-radius: 2px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(0,0,0,0.12);
}
.bb-tricolor span { flex: 1; }
.bb-tricolor .b { background: #1C1B19; }
.bb-tricolor .r { background: var(--red); }
.bb-tricolor .g { background: var(--gold); }
.bb-tagline {
    font-family: 'Space Mono', monospace;
    font-size: 0.66rem;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin: 0;
}

/* ── Suggestion chips — clear paper cards (not the old faded look) ───────── */
[data-testid="stButton"] > button {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 12px !important;
    color: var(--ink) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 0.7rem 0.7rem !important;
    text-align: left !important;
    justify-content: flex-start !important;
    width: 100% !important;
    white-space: normal !important;
    overflow: visible !important;
    word-break: break-word !important;
    line-height: 1.4 !important;
    box-shadow: 0 1px 2px rgba(28,27,25,0.04) !important;
    transition: border-color 0.15s, box-shadow 0.15s, transform 0.1s !important;
}
[data-testid="stButton"] > button:hover {
    border-color: var(--gold) !important;
    box-shadow: 0 3px 12px rgba(184,144,43,0.16) !important;
    transform: translateY(-1px) !important;
    color: var(--ink) !important;
}
[data-testid="stButton"] > button:active { transform: translateY(0) !important; }

/* Popover trigger (ℹ info button) — circular */
[data-testid="stPopover"] button,
[data-testid="stPopover"] > button {
    background: #1C1B19 !important;
    border: 1.5px solid rgba(255,255,255,0.35) !important;
    border-radius: 50% !important;
    color: #ffffff !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.82rem !important;
    width: 32px !important;
    min-width: 32px !important;
    height: 32px !important;
    padding: 0 !important;
    justify-content: center !important;
    align-items: center !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: unset !important;
    margin-top: 0.35rem !important;
    box-shadow: none !important;
}
[data-testid="stPopover"] button p,
[data-testid="stPopover"] button span {
    color: #ffffff !important;
}
[data-testid="stPopover"] button:hover,
[data-testid="stPopover"] > button:hover {
    background: #2e2d2a !important;
    border-color: var(--gold) !important;
    color: var(--gold) !important;
    transform: none !important;
}

/* Clear-chat button (below the form) — quiet text link */
.element-container:has([data-testid="stForm"]) ~ div [data-testid="stButton"] > button,
.element-container:has([data-testid="stForm"]) ~ [data-testid="stColumns"] [data-testid="stButton"] > button {
    background: transparent !important;
    border: none !important;
    color: var(--ink-faint) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.4px !important;
    padding: 0.2rem 0.5rem !important;
    border-radius: 4px !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: unset !important;
    justify-content: center !important;
    text-align: center !important;
    box-shadow: none !important;
}
.element-container:has([data-testid="stForm"]) ~ div [data-testid="stButton"] > button:hover,
.element-container:has([data-testid="stForm"]) ~ [data-testid="stColumns"] [data-testid="stButton"] > button:hover {
    color: var(--red) !important;
    background: transparent !important;
    transform: none !important;
    box-shadow: none !important;
}

/* Remove spacing between chip rows */
[data-testid="stVerticalBlock"] > div > [data-testid="stButton"] {
    margin-bottom: 0 !important;
}

/* ── Search bar (stForm) ─────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: var(--surface) !important;
    border: 1.5px solid var(--line) !important;
    border-radius: 16px !important;
    padding: 0.35rem 0.55rem !important;
    box-shadow: 0 4px 18px rgba(28,27,25,0.07) !important;
    margin-top: 0.25rem !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
[data-testid="stForm"]:focus-within {
    border-color: var(--gold) !important;
    box-shadow: 0 4px 20px rgba(184,144,43,0.18) !important;
}
[data-testid="stForm"] > div,
[data-testid="stForm"] [data-testid="stVerticalBlock"] { gap: 0 !important; }
[data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    align-items: center !important;
    gap: 0.4rem !important;
}

/* Text input */
[data-testid="stForm"] [data-baseweb="input"],
[data-testid="stForm"] [data-testid="stTextInputRootElement"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
[data-testid="stForm"] input[type="text"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: var(--ink) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.98rem !important;
    caret-color: var(--gold-deep);
}
[data-testid="stForm"] input[type="text"]:focus { box-shadow: none !important; }
[data-testid="stForm"] input::placeholder { color: var(--ink-faint) !important; }

/* Hide "Press Enter to submit form" label */
[data-testid="InputInstructions"],
[data-testid="stForm"] small,
[data-testid="stForm"] [data-testid="stTextInput"] small {
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
}

/* Send button ↑ */
[data-testid="stFormSubmitButton"] > button {
    background: var(--gold) !important;
    border: none !important;
    border-radius: 11px !important;
    color: #fff !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    padding: 0.28rem 0.85rem !important;
    height: 38px !important;
    white-space: nowrap !important;
    width: auto !important;
    box-shadow: 0 2px 6px rgba(184,144,43,0.3) !important;
    transition: background 0.15s, transform 0.1s !important;
}
[data-testid="stFormSubmitButton"] > button:hover {
    background: var(--gold-deep) !important;
    transform: translateY(-1px) !important;
}
[data-testid="stFormSubmitButton"] > button:active { transform: translateY(0) !important; }

/* ── Answer eyebrow (the per-message federal marker) ─────────────────────── */
.bb-eyebrow {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 1.4rem 0 0.3rem;
}
.bb-flag {
    display: inline-flex;
    width: 22px;
    height: 11px;
    border-radius: 2px;
    overflow: hidden;
    box-shadow: 0 1px 1.5px rgba(0,0,0,0.18);
    flex-shrink: 0;
}
.bb-flag span { flex: 1; }
.bb-flag .b { background: #1C1B19; }
.bb-flag .r { background: var(--red); }
.bb-flag .g { background: var(--gold); }
.bb-eyebrow-label {
    font-family: 'Space Mono', monospace;
    font-size: 0.64rem;
    font-weight: 700;
    letter-spacing: 1.8px;
    text-transform: uppercase;
    color: var(--ink-faint);
}

/* ── Chat message typography ─────────────────────────────────────────────── */
p, li {
    color: var(--ink) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.97rem !important;
    line-height: 1.7 !important;
}
h1, h2, h3, h4, h5, h6 {
    color: var(--ink) !important;
    font-family: 'Bricolage Grotesque', sans-serif !important;
    letter-spacing: -0.3px !important;
}
strong { color: var(--ink) !important; font-weight: 600 !important; }
a { color: var(--gold-deep) !important; }
code:not(pre > code) {
    background: rgba(184,144,43,0.14) !important;
    border-radius: 4px !important;
    padding: 0.1rem 0.38rem !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.84em !important;
    color: var(--gold-deep) !important;
}
pre {
    background: var(--surface) !important;
    border: 1px solid var(--line) !important;
    border-radius: 10px !important;
    padding: 1rem !important;
    overflow-x: auto !important;
}
pre > code {
    background: transparent !important;
    color: var(--ink) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.84rem !important;
    padding: 0 !important;
}
blockquote {
    border-left: 3px solid var(--gold) !important;
    padding-left: 0.85rem !important;
    margin-left: 0 !important;
    color: var(--ink-soft) !important;
}

/* Data tables — clean ledger look on white */
table {
    border-collapse: collapse !important;
    width: 100% !important;
    background: var(--surface) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    box-shadow: 0 1px 3px rgba(28,27,25,0.06) !important;
    font-family: 'Inter', sans-serif !important;
}
th, td {
    border-bottom: 1px solid var(--line-soft) !important;
    border-left: none !important;
    border-right: none !important;
    padding: 0.5rem 0.85rem !important;
    text-align: left !important;
}
th {
    background: rgba(28,27,25,0.04) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.6px !important;
    text-transform: uppercase !important;
    color: var(--ink-soft) !important;
}
td:not(:first-child) { font-variant-numeric: tabular-nums !important; }

/* Spinner */
[data-testid="stSpinner"] p {
    color: var(--gold-deep) !important;
    font-family: 'Space Mono', monospace !important;
    font-size: 0.82rem !important;
    letter-spacing: 0.4px !important;
}
[data-testid="stSpinner"] svg { stroke: var(--gold) !important; }

/* Info popover panel — force light surface on the panel AND every inner
   container (Streamlit nests the content in wrappers that otherwise keep a
   dark fill), and dark ink on all text. NOTE: target only the popover BODY,
   never [data-testid="stPopover"] (that's the trigger button). */
[data-testid="stPopoverBody"],
[data-testid="stPopoverBody"] > div,
[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"],
[data-testid="stPopoverBody"] [data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"] {
    background: var(--surface) !important;
    background-color: var(--surface) !important;
}
[data-testid="stPopoverBody"] {
    border: 1px solid var(--line) !important;
    border-radius: 12px !important;
}
[data-testid="stPopoverBody"] p,
[data-testid="stPopoverBody"] li,
[data-testid="stPopoverBody"] strong,
[data-testid="stPopoverBody"] h1,
[data-testid="stPopoverBody"] h2,
[data-testid="stPopoverBody"] h3 {
    color: var(--ink) !important;
}
[data-testid="stPopoverBody"] strong { font-weight: 600 !important; }
</style>
"""

# ── Message HTML ──────────────────────────────────────────────────────────────
# User question: solid ink bubble, right-aligned.
_USER_BUBBLE: str = (
    '<div style="display:flex;justify-content:flex-end;margin:1.4rem 0 0.2rem;">'
    '<div style="background:#1C1B19;border-radius:16px 16px 4px 16px;'
    "padding:0.6rem 1.05rem;max-width:80%;color:#F1EFE9;"
    "font-family:\'Inter\',sans-serif;font-size:0.95rem;line-height:1.55;"
    'word-wrap:break-word;box-shadow:0 2px 8px rgba(28,27,25,0.16);">'
    "{content}"
    "</div></div>"
)

# Assistant answer: federal tricolour eyebrow above typeset markdown.
_ASSISTANT_EYEBROW: str = (
    '<div class="bb-eyebrow">'
    '<span class="bb-flag"><span class="b"></span><span class="r"></span>'
    '<span class="g"></span></span>'
    '<span class="bb-eyebrow-label">Parlamentsdaten</span>'
    "</div>"
)


def _render_user_msg(content: str) -> None:
    escaped = _html.escape(content).replace("\n", "<br>")
    st.markdown(_USER_BUBBLE.format(content=escaped), unsafe_allow_html=True)


def _render_assistant_msg(content: str) -> None:
    st.markdown(_ASSISTANT_EYEBROW, unsafe_allow_html=True)
    st.markdown(content)
    st.markdown('<div style="height:0.4rem;"></div>', unsafe_allow_html=True)


def _group_into_exchanges(
    messages: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    exchanges: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(messages):
        if messages[i]["role"] == "user":
            pair: list[dict[str, Any]] = [messages[i]]
            if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
                pair.append(messages[i + 1])
                i += 2
            else:
                i += 1
            exchanges.append(pair)
        else:
            i += 1
    return exchanges


# ── Async bridge ──────────────────────────────────────────────────────────────
def _run_async(coro: Any) -> Any:
    result: list[Any] = [None]
    exc: list[BaseException | None] = [None]

    def _worker() -> None:
        try:
            result[0] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            exc[0] = e

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()

    if exc[0] is not None:
        raise exc[0]
    return result[0]


# ── Chat turn processor ───────────────────────────────────────────────────────
def _process_chat_turn(
    llm_messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    async def _run() -> tuple[str, list[dict[str, Any]]]:
        new_msgs: list[dict[str, Any]] = []

        async with GroqClient(settings) as llm:
            resp = await llm.chat_with_tools(llm_messages, TOOL_SCHEMAS)
            choice = resp.choices[0]

            if choice.finish_reason == "tool_calls":
                tool_calls = choice.message.tool_calls or []
                asst_msg: dict[str, Any] = {
                    "role": "assistant",
                    "content": choice.message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
                new_msgs.append(asst_msg)
                extended = llm_messages + new_msgs

                for tc in tool_calls:
                    try:
                        tool_args: dict[str, Any] = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}
                    result_str = await _dispatch_tool(tc.function.name, tool_args)
                    tool_msg: dict[str, Any] = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_str,
                    }
                    new_msgs.append(tool_msg)
                    extended.append(tool_msg)

                final = await llm.chat_with_tools(extended, TOOL_SCHEMAS)
                answer = final.choices[0].message.content or ""
            else:
                answer = choice.message.content or ""

        return answer, new_msgs

    return _run_async(_run())


# ── System message builder ────────────────────────────────────────────────────
def _system_message() -> dict[str, str]:
    content = (
        CHAT_SYSTEM_PROMPT
        + "\n\nDefault Wahlperiode for all tool calls: 20. "
        "Use this unless the user specifies a different period in their question."
    )
    return {"role": "system", "content": content}


# ── Session-state initialisation ──────────────────────────────────────────────
def _init_state() -> None:
    defaults: dict[str, Any] = {
        "llm_messages": [_system_message()],
        "display_messages": [],
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ── Main app ──────────────────────────────────────────────────────────────────
def main() -> None:
    _init_state()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Consume pending prompt set during the previous rerun (form/chip submit)
    prompt_to_process: str | None = st.session_state.get("_pending_prompt")
    if "_pending_prompt" in st.session_state:
        del st.session_state["_pending_prompt"]

    has_messages = bool(st.session_state.display_messages)

    # ── Header + ℹ info popover ───────────────────────────────────────────────
    _, title_col, info_col = st.columns([0.3, 11, 1])
    with title_col:
        st.markdown(
            '<div class="bb-header">'
            '<span class="bb-title">BundesBot</span>'
            '<span class="bb-tricolor"><span class="b"></span>'
            '<span class="r"></span><span class="g"></span></span>'
            '<span class="bb-tagline">Deutscher Bundestag · Open Data</span>'
            "</div>",
            unsafe_allow_html=True,
        )
    with info_col, st.popover("ℹ"):
        st.markdown(INFO_TEXT)

    # ── Landing spacer — only on blank-slate view ─────────────────────────────
    if not has_messages and not prompt_to_process:
        st.markdown(
            '<div style="height:max(0px,calc(50vh - 320px));"></div>',
            unsafe_allow_html=True,
        )

    # ── Chat history (oldest first, all above the search bar) ─────────────────
    if has_messages:
        for exchange in _group_into_exchanges(st.session_state.display_messages):
            for msg in exchange:
                if msg["role"] == "user":
                    _render_user_msg(msg["content"])
                else:
                    _render_assistant_msg(msg["content"])

    # ── Process new prompt (renders inline, above the form) ───────────────────
    if prompt_to_process:
        _render_user_msg(prompt_to_process)

        with st.spinner("Reading parliamentary data…"):
            try:
                msgs_for_api = copy.deepcopy(st.session_state.llm_messages)
                msgs_for_api.append({"role": "user", "content": prompt_to_process})
                answer, intermediate = _process_chat_turn(msgs_for_api)
            except Exception as exc:
                log.error("Chat turn failed: %s", exc)
                answer = f"⚠ Error communicating with Groq: {exc}"
                intermediate = []

        if not answer.strip():
            answer = "_Sorry, I couldn't generate a response for that. Try rephrasing._"
        _render_assistant_msg(answer)

        # Persist to session state
        st.session_state.llm_messages.append({"role": "user", "content": prompt_to_process})
        st.session_state.llm_messages.extend(intermediate)
        st.session_state.llm_messages.append({"role": "assistant", "content": answer})
        st.session_state.display_messages.append({"role": "user", "content": prompt_to_process})
        st.session_state.display_messages.append({"role": "assistant", "content": answer})

        turn_count = len(st.session_state.display_messages)
        if turn_count > 0 and turn_count % GC_TRIGGER_EVERY_N_TURNS == 0:
            gc.collect()

    # ── Gap before chips/form ─────────────────────────────────────────────────
    st.markdown('<div style="height:0.5rem;"></div>', unsafe_allow_html=True)

    # ── Hint chips — 3 side-by-side boxes, only on landing ───────────────────
    if not has_messages and not prompt_to_process:
        c1, c2, c3 = st.columns(3)
        for col, chip, idx in zip([c1, c2, c3], HINT_CHIPS, range(3), strict=True):
            with col:
                st.button(
                    chip,
                    key=f"chip_{idx}",
                    use_container_width=True,
                    on_click=lambda c=chip: st.session_state.update({"_pending_prompt": c}),
                )

    # ── Search bar form ───────────────────────────────────────────────────────
    with st.form("search_form", clear_on_submit=True):
        col_input, col_send = st.columns([6, 1])

        with col_input:
            user_input: str = st.text_input(
                "query",
                placeholder="Ask about the Bundestag…",
                label_visibility="collapsed",
            )

        with col_send:
            submitted = st.form_submit_button("↑", use_container_width=True)

    # ── Handle form submission — store in state and rerun ─────────────────────
    if submitted and user_input.strip():
        st.session_state["_pending_prompt"] = user_input.strip()
        st.rerun()

    # ── Clear chat — always below the search bar ─────────────────────────────
    _, col_clr, _ = st.columns([4, 2, 4])
    with col_clr:
        if st.button("Clear chat", use_container_width=True, key="clear_btn"):
            st.session_state.display_messages = []
            st.session_state.llm_messages = [_system_message()]
            st.session_state.pop("_pending_prompt", None)
            gc.collect()
            st.rerun()


if __name__ == "__main__":
    main()
