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
**BundesBot** is an AI assistant for exploring German parliamentary (Bundestag) data.

**What you can ask:**
- Fraktion distributions across Wahlperioden
- Profiles of Members of the Bundestag (MdBs)
- Party representation and legislative activity
- Debates, committees, and voting records

**How to use:**
- Type your question and press **↑** or hit **Enter**
- Use the pill selector to change the default Wahlperiode (election period 1–20)
- Click the suggestion chips to try an example question

**Data source:** Bundestag Open Data API (DIP)
**AI model:** Groq (LLaMA-based tool-calling)

"""

# ── Custom CSS ────────────────────────────────────────────────────────────────
CUSTOM_CSS: str = """
<style>
/* ── Base ─────────────────────────────────────────────────────────────────── */
html, body, .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
    background-color: #0d1117 !important;
}
.block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 680px !important;
    padding-left: 1.5rem !important;
    padding-right: 1.5rem !important;
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

/* ── Header ──────────────────────────────────────────────────────────────── */
.bb-header {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding-bottom: 0.9rem;
}
.bb-logo  { font-size: 2.3rem; line-height: 1; }
.bb-title {
    font-size: 2.2rem;
    font-weight: 800;
    color: #ffffff;
    letter-spacing: -0.5px;
    line-height: 1;
}

/* ── Hint chip buttons — horizontal row, small faded style ──────────────── */
[data-testid="stButton"] > button {
    background: #161b22 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 10px !important;
    color: rgba(230,237,243,0.30) !important;
    font-size: 0.65rem !important;
    padding: 0.35rem 0.6rem !important;
    text-align: center !important;
    justify-content: center !important;
    width: 100% !important;
    white-space: normal !important;
    overflow: visible !important;
    word-break: break-word !important;
    line-height: 1.35 !important;
    transition: color 0.15s, border-color 0.15s !important;
}
[data-testid="stButton"] > button:hover {
    background: rgba(255,255,255,0.04) !important;
    border-color: rgba(255,255,255,0.2) !important;
    color: rgba(230,237,243,0.58) !important;
}

/* Popover trigger (ℹ info button) — circular icon style */
[data-testid="stPopover"] > button {
    background: transparent !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 50% !important;
    color: rgba(230,237,243,0.45) !important;
    font-size: 0.85rem !important;
    width: 30px !important;
    min-width: 30px !important;
    height: 30px !important;
    padding: 0 !important;
    justify-content: center !important;
    align-items: center !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: unset !important;
    margin-top: 0.55rem !important;
}
[data-testid="stPopover"] > button:hover {
    background: rgba(255,255,255,0.05) !important;
    border-color: rgba(255,255,255,0.3) !important;
    color: rgba(230,237,243,0.85) !important;
}

/* Clear chat button (below the form) — text link style */
.element-container:has([data-testid="stForm"]) ~ div [data-testid="stButton"] > button,
.element-container:has([data-testid="stForm"]) ~ [data-testid="stColumns"] [data-testid="stButton"] > button {
    background: transparent !important;
    border: none !important;
    color: rgba(230,237,243,0.24) !important;
    font-size: 0.75rem !important;
    padding: 0.2rem 0.5rem !important;
    border-radius: 4px !important;
    white-space: nowrap !important;
    overflow: visible !important;
    text-overflow: unset !important;
    justify-content: center !important;
    text-align: center !important;
}
.element-container:has([data-testid="stForm"]) ~ div [data-testid="stButton"] > button:hover,
.element-container:has([data-testid="stForm"]) ~ [data-testid="stColumns"] [data-testid="stButton"] > button:hover {
    color: rgba(230,237,243,0.5) !important;
    background: rgba(255,255,255,0.04) !important;
}

/* ── Remove spacing between chip rows ────────────────────────────────────── */
[data-testid="stVerticalBlock"] > div > [data-testid="stButton"] {
    margin-bottom: 0 !important;
}

/* ── Search bar (stForm) ─────────────────────────────────────────────────── */
[data-testid="stForm"] {
    background: #161b22 !important;
    border: 1.5px solid rgba(255,255,255,0.12) !important;
    border-radius: 14px !important;
    padding: 0.3rem 0.55rem !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6) !important;
    margin-top: 0.25rem !important;
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
    color: #e6edf3 !important;
    font-size: 0.95rem !important;
    caret-color: #58a6ff;
}
[data-testid="stForm"] input[type="text"]:focus { box-shadow: none !important; }
[data-testid="stForm"] input::placeholder { color: rgba(230,237,243,0.28) !important; }

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
    background: #1f6feb !important;
    border: none !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    padding: 0.28rem 0.85rem !important;
    height: 34px !important;
    white-space: nowrap !important;
    width: auto !important;
    transition: background 0.15s !important;
}
[data-testid="stFormSubmitButton"] > button:hover { background: #388bfd !important; }

/* ── Divider ─────────────────────────────────────────────────────────────── */
hr { border-color: rgba(255,255,255,0.07) !important; margin: 0.8rem 0 !important; }

/* ── Chat message typography ─────────────────────────────────────────────── */
p, li { color: #e6edf3 !important; font-size: 0.95rem !important; line-height: 1.68 !important; }
h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
strong { color: #ffffff !important; }
code:not(pre > code) {
    background: rgba(110,118,129,0.35) !important;
    border-radius: 4px !important;
    padding: 0.12rem 0.38rem !important;
    font-size: 0.87em !important;
    color: #e6edf3 !important;
}
pre {
    background: #161b22 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    padding: 1rem !important;
    overflow-x: auto !important;
}
pre > code { background: transparent !important; color: #e6edf3 !important; font-size: 0.86rem !important; padding: 0 !important; }
blockquote { border-left: 3px solid rgba(88,166,255,0.45) !important; padding-left: 0.75rem !important; margin-left: 0 !important; }
table { border-collapse: collapse !important; width: 100% !important; }
th, td { border: 1px solid rgba(255,255,255,0.1) !important; padding: 0.45rem 0.75rem !important; }
th { background: rgba(255,255,255,0.05) !important; }
[data-testid="stSpinner"] p { color: #58a6ff !important; font-size: 0.88rem !important; }
</style>
"""

# ── Message HTML ──────────────────────────────────────────────────────────────
_USER_BUBBLE: str = (
    '<div style="display:flex;justify-content:flex-end;margin:0.9rem 0 0.4rem;">'
    '<div style="background:#1e2433;border:1px solid rgba(255,255,255,0.09);'
    "border-radius:18px 18px 4px 18px;padding:0.65rem 1.05rem;"
    'max-width:82%;color:#e6edf3;font-size:0.95rem;line-height:1.65;word-wrap:break-word;">'
    "{content}"
    "</div></div>"
)


def _render_user_msg(content: str) -> None:
    escaped = _html.escape(content).replace("\n", "<br>")
    st.markdown(_USER_BUBBLE.format(content=escaped), unsafe_allow_html=True)


def _render_assistant_msg(content: str) -> None:
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
            '<span class="bb-logo">🏛️</span>'
            '<span class="bb-title">BundesBot</span>'
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

        with st.spinner("Thinking…"):
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
                placeholder="Ask anything",
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
