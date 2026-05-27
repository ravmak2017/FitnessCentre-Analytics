"""Guided Q&A Chat — branded with PDF transcript export."""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic
import streamlit as st
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env", override=True)

from llm_client import SEED_QUESTIONS_EN, ask_qa
from pdf_export import chat_to_pdf
from prompts import SYSTEM_PROMPT_QA
from qa_context import build_full_context
from theme import (
    ACCENT,
    ACCENT_DEEP,
    BG_PANEL,
    BORDER,
    TEXT_MID,
    TEXT_MUTED,
    brand_bar,
    get_lang,
    inject_theme,
    quote_banner,
    show_logo,
    sidebar_branding,
    t,
)

st.set_page_config(page_title="Q&A Chat · ABC", page_icon="💬", layout="wide")
inject_theme()
sidebar_branding()

from data_sources import require_master_or_stop
require_master_or_stop()

SEED_QUESTIONS = {
    "en": SEED_QUESTIONS_EN,
    "hi": [
        "FY2025-26 का सारांश दीजिए",
        "किन महीनों में नुकसान या डेटा समस्याएँ थीं?",
        "हमारा सबसे अच्छा महीना कौन सा था और क्यों?",
        "तिमाही के अनुसार रेवेन्यू का ट्रेंड कैसा था?",
        "Q1 (अप्रैल-जून) और Q4 (जनवरी-मार्च) की तुलना",
    ],
}


def current_seeds():
    return SEED_QUESTIONS.get(get_lang(), SEED_QUESTIONS["en"])


@st.cache_data
def get_context():
    ctx, meta = build_full_context()
    return SYSTEM_PROMPT_QA + "\n\n" + ctx, meta


# Initialize state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "next_questions" not in st.session_state:
    st.session_state.next_questions = current_seeds().copy()
if "usage" not in st.session_state:
    st.session_state.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}


# ─── Sidebar ────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"### {t('chat_controls')}")
    if st.button(t("back_to_start"), use_container_width=True):
        st.session_state.messages = []
        st.session_state.next_questions = current_seeds().copy()
        st.rerun()
    if st.button(t("clear_chat"), use_container_width=True):
        st.session_state.messages = []
        st.session_state.next_questions = current_seeds().copy()
        st.session_state.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        st.rerun()

    # Export PDF directly
    if st.session_state.messages:
        try:
            pdf_bytes = chat_to_pdf(
                st.session_state.messages,
                title="Q&A Chat Transcript",
                subtitle=f"ABC · {datetime.now().strftime('%d %b %Y, %H:%M')}",
            )
            st.download_button(
                t("export_pdf"), data=pdf_bytes,
                file_name=f"qa_chat_{datetime.now().strftime('%Y-%m-%d_%H%M')}.pdf",
                mime="application/pdf", use_container_width=True,
                key="dl_chat_pdf",
            )
        except Exception as e:
            st.caption(f"⚠ PDF: {e}")
    else:
        st.button(t("export_pdf"), use_container_width=True, disabled=True, key="dl_chat_pdf_dis")

    st.markdown("---")
    st.markdown(f"### {t('tokens_used')}")
    st.caption(f"{t('input_tokens')}: {st.session_state.usage['input']:,}")
    st.caption(f"{t('output_tokens')}: {st.session_state.usage['output']:,}")
    st.caption(f"{t('cache_hits')}: {st.session_state.usage['cache_read']:,}")


# ─── Main ───────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 5])
with col_logo:
    show_logo(width=120)
with col_title:
    st.title(f"4. {t('page_qa_title')}")
    st.markdown(
        f'<div style="color:{TEXT_MUTED}; font-size:0.95rem; font-weight:500;">'
        f'{t("page_qa_sub")}</div>',
        unsafe_allow_html=True,
    )

quote_banner()

try:
    system_prompt, meta = get_context()
except Exception as e:
    st.error(f"⚠️ Could not build context: {e}")
    st.stop()

# Context status banner
st.markdown(
    f'<div style="background:{BG_PANEL}; border:1px solid {BORDER}; '
    f'border-left:3px solid {ACCENT}; padding:0.8rem 1.2rem; border-radius:8px; '
    f'margin-bottom:1rem;">'
    f'<span style="color:{ACCENT_DEEP}; font-weight:600;">{t("kb_loaded")}</span> '
    f'<span style="color:{TEXT_MID};">'
    f'{t("months_briefs_meta", months=meta["months"], briefs=meta["briefs_count"], tokens=f"{meta["context_chars"]//4:,}")}'
    f'</span></div>',
    unsafe_allow_html=True,
)


def ask_llm(question: str):
    st.session_state.messages.append({"role": "user", "content": question})
    try:
        data, usage = ask_qa(system_prompt, st.session_state.messages)
        answer = data.get("answer", "(no answer)")
        next_qs = data.get("next_questions") or []
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.session_state.next_questions = next_qs[:5] if next_qs else current_seeds()
        st.session_state.usage["input"] += usage["input_tokens"]
        st.session_state.usage["output"] += usage["output_tokens"]
        st.session_state.usage["cache_read"] += usage["cache_read_input_tokens"]
        st.session_state.usage["cache_write"] += usage["cache_creation_input_tokens"]
    except anthropic.AuthenticationError:
        st.error(t("err_no_key"))
        st.session_state.messages.pop()
    except anthropic.RateLimitError as e:
        st.error(f"{t('err_rate_limit')} {e}")
        st.session_state.messages.pop()
    except anthropic.APIStatusError as e:
        st.error(f"{t('err_api')} {e.status_code}: {e.message}")
        st.session_state.messages.pop()
    except json.JSONDecodeError as e:
        st.error(f"{t('err_parse')} {e}")
        st.session_state.messages.pop()


# Render chat history
if st.session_state.messages:
    st.markdown("---")
    for m in st.session_state.messages:
        with st.chat_message(m["role"], avatar="🧑" if m["role"] == "user" else "🤖"):
            st.markdown(m["content"])

# Question buttons
st.markdown("---")
header_text = t("pick_question") if not st.session_state.messages else t("dig_deeper")
st.markdown(header_text)

qs = st.session_state.next_questions[:5]
if qs:
    cols = st.columns(2)
    for i, q in enumerate(qs):
        with cols[i % 2]:
            if st.button(q, key=f"q_{i}_{len(st.session_state.messages)}",
                          use_container_width=True):
                with st.spinner(t("asking_claude")):
                    ask_llm(q)
                st.rerun()

# Custom input
prompt = st.chat_input(t("chat_placeholder"))
if prompt:
    with st.spinner(t("asking_claude")):
        ask_llm(prompt)
    st.rerun()

# Footer
st.markdown("---")
brand_bar(t("brand_bar_qa"))
