"""
03_coding.py — Core coding workspace
=====================================

The analyst's primary working environment:
- Browse segments from a selected source
- Apply codes manually
- Request and review AI suggestions
- Write memos
- Find similar segments via vector search
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Coding | Thematic Analysis", layout="wide")


def _get_llm():
    return st.session_state.get("llm")


def _get_db():
    factory = st.session_state.get("db_session_factory")
    return factory() if factory else None


def render_segment_card(seg: dict, codes: list[str]) -> None:
    """Render one segment with its coding controls."""
    speaker = seg.get("speaker", "")
    start = seg.get("start_s")
    text = seg.get("text", "")

    speaker_color = "#0F6E56" if speaker == "INTERVIEWEE" else "#534AB7"
    time_label = f"  {start:.0f}s" if start is not None else ""

    st.markdown(
        f"<span style='color:{speaker_color};font-weight:500'>{speaker}</span>"
        f"<span style='color:#888;font-size:12px'>{time_label}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(f"> {text}")

    col_codes, col_ai, col_memo = st.columns([2, 1, 1])

    with col_codes:
        selected = st.multiselect(
            "Apply codes",
            options=codes,
            key=f"codes_{seg['id']}",
            label_visibility="collapsed",
            placeholder="Select codes to apply…",
        )
        if selected and st.button("Apply", key=f"apply_{seg['id']}"):
            st.success(f"Applied: {', '.join(selected)}")

    with col_ai:
        if st.button("AI suggest", key=f"ai_{seg['id']}"):
            llm = _get_llm()
            if llm is None:
                st.error("No LLM configured.")
            else:
                with st.spinner("Requesting suggestions…"):
                    try:
                        suggestions = llm.suggest_codes(
                            segment_text=text,
                            existing_codes=codes,
                            codebook_context=st.session_state.get("codebook_context", ""),
                            project_id=st.session_state.get("active_project_id", ""),
                        )
                        st.session_state[f"suggestions_{seg['id']}"] = suggestions
                    except Exception as exc:
                        st.error(f"LLM error: {exc}")

    with col_memo:
        if st.button("Memo", key=f"memo_{seg['id']}"):
            st.session_state[f"show_memo_{seg['id']}"] = True

    # ── AI suggestions ────────────────────────────────────────────────────────
    suggestions = st.session_state.get(f"suggestions_{seg['id']}", [])
    if suggestions:
        st.markdown("**AI suggestions** (all pending — review each one)")
        for i, s in enumerate(suggestions):
            with st.container(border=True):
                confidence = s.get("confidence", 0.0)
                label = s.get("label", "?")
                justification = s.get("justification", "")
                is_new = s.get("is_new_code", False)

                badge = " ✦ new code" if is_new else ""
                st.markdown(
                    f"**{label}**{badge} — confidence: {confidence:.0%}"
                )
                st.caption(justification)
                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("Accept", key=f"accept_{seg['id']}_{i}"):
                        st.success(f"Accepted '{label}'. Added to decisions.")
                        suggestions.pop(i)
                        st.rerun()
                with col_r:
                    if st.button("Reject", key=f"reject_{seg['id']}_{i}"):
                        suggestions.pop(i)
                        st.rerun()

    # ── Memo input ────────────────────────────────────────────────────────────
    if st.session_state.get(f"show_memo_{seg['id']}"):
        memo_text = st.text_area("Memo", key=f"memo_text_{seg['id']}", height=80)
        if st.button("Save memo", key=f"save_memo_{seg['id']}"):
            if memo_text.strip():
                st.success("Memo saved.")
            st.session_state[f"show_memo_{seg['id']}"] = False

    st.divider()


# ─────────────────────────────────────────────
#  Main page
# ─────────────────────────────────────────────


st.title("Coding workspace")

# Sidebar controls
with st.sidebar:
    st.subheader("Session settings")
    analyst = st.text_input("Analyst name", value="analyst")
    st.session_state["analyst"] = analyst

    codebook_context = st.text_area(
        "Research question / codebook context",
        value=st.session_state.get("codebook_context", ""),
        help="Passed to the AI model with every suggestion request.",
        height=80,
    )
    st.session_state["codebook_context"] = codebook_context

    st.divider()
    st.caption("Source filter")
    speaker_filter = st.selectbox(
        "Show speaker",
        ["INTERVIEWEE only", "All speakers"],
        index=0,
    )

# Placeholder segments for demo (replace with DB query)
demo_segments = [
    {
        "id": "seg-001",
        "speaker": "INTERVIEWEE",
        "start_s": 45.0,
        "text": (
            "Nos quitaron el espacio sin consultarnos. Llevábamos tres años "
            "trabajando en ese salón comunitario y de un día para otro nos dijeron "
            "que ya no podíamos usarlo."
        ),
    },
    {
        "id": "seg-002",
        "speaker": "INTERVIEWEE",
        "start_s": 123.5,
        "text": (
            "La comunidad se organizó de todas formas. Empezamos a reunirnos en "
            "casas particulares, rotando cada semana para no cargar a una sola familia."
        ),
    },
    {
        "id": "seg-003",
        "speaker": "INTERVIEWER",
        "start_s": 180.2,
        "text": "¿Y cómo respondió la institución cuando reclamaron el espacio?",
    },
]

demo_codes = [
    "exclusion_from_spaces",
    "community_self_organization",
    "institutional_response",
    "loss_of_autonomy",
    "solidarity_practices",
]

# Filter by speaker
if speaker_filter == "INTERVIEWEE only":
    visible = [s for s in demo_segments if s.get("speaker") == "INTERVIEWEE"]
else:
    visible = demo_segments

col_main, col_similar = st.columns([3, 1])

with col_main:
    st.subheader(f"Segments ({len(visible)} shown)")
    for seg in visible:
        render_segment_card(seg, demo_codes)

with col_similar:
    st.subheader("Similar segments")
    query = st.text_input("Search by text", placeholder="Type a concept…")
    if query and st.button("Find similar"):
        llm = _get_llm()
        st.caption("Vector search results will appear here once embeddings are built.")
