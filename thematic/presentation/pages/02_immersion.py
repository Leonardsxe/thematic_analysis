"""
02_immersion.py — Immersion workspace
=======================================

Reading-first space for familiarising with transcript material before
formal coding begins. Supports memos, bookmarks, and audio playback alignment.
"""

from __future__ import annotations

import streamlit as st
from thematic.presentation.translations import t
from thematic.infrastructure.db.repositories import (
    SqlSourceRepository,
    SqlSegmentRepository,
)

# ── Infrastructure ────────────────────────────────────────────────────────────
def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised. Please check app.py.")
        st.stop()
    return factory()

st.set_page_config(page_title=f"{t('nav_immersion')} | {t('nav_title')}", layout="wide")

st.title("Immersion")
st.caption(
    "Read and familiarise yourself with the material before coding. "
    "Write memos, highlight passages, and note initial impressions."
)

# ── Source selector ───────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader(t('nav_immersion'))
    
    active_corpus_id = st.session_state.get("active_corpus_id")
    if not active_corpus_id:
        st.warning("Please select a project and corpus first in the 'Corpus' page.")
        st.stop()

    session = get_session()
    source_repo = SqlSourceRepository(session)
    segment_repo = SqlSegmentRepository(session)
    
    all_sources = source_repo.list_for_corpus(active_corpus_id)
    source_titles = [s.title for s in all_sources]
    
    if not source_titles:
        st.info("No sources found in this corpus.")
        session.close()
        st.stop()

    selected_title = st.selectbox(t('nav_corpus'), source_titles)
    active_source = next(s for s in all_sources if s.title == selected_title)
    
    speaker_filter = st.multiselect(
        "Show speakers", ["INTERVIEWEE", "INTERVIEWER"], default=["INTERVIEWEE"]
    )
    st.divider()
    show_timestamps = st.checkbox("Show timestamps", value=True)
    st.divider()
    st.subheader("Quick memo")
    quick_memo = st.text_area("General impression", height=100, placeholder="Initial thoughts…")
    if st.button("Save memo"):
        st.info("General memos not implemented in DB yet.")

# ── Load real segments ────────────────────────────────────────────────────────
segments = segment_repo.list_for_source(active_source.id)
visible = [s for s in segments if s.speaker in speaker_filter]

st.subheader(f"{active_source.title} — {len(visible)} segments")

for i, seg in enumerate(visible):
    with st.container(border=False):
        speaker = seg.speaker
        color = "#0F6E56" if speaker == "INTERVIEWEE" else "#534AB7"
        time_label = ""
        if show_timestamps and seg.start_s is not None:
            t_val = int(seg.start_s)
            time_label = f" · {t_val//60}:{t_val%60:02d}"

        st.markdown(
            f"<span style='color:{color};font-weight:500;font-size:13px'>"
            f"{speaker}{time_label}</span>",
            unsafe_allow_html=True,
        )
        st.markdown(seg.text)

        col_memo, col_bookmark = st.columns([3, 1])
        with col_memo:
            if st.button("Add memo", key=f"memo_{i}"):
                st.session_state[f"open_memo_{i}"] = True
        with col_bookmark:
            if st.button("Bookmark", key=f"bm_{i}"):
                st.success("Bookmarked.")

        if st.session_state.get(f"open_memo_{i}"):
            memo_text = st.text_area("Memo for this passage", key=f"memo_txt_{i}", height=70)
            if st.button("Save", key=f"save_memo_{i}"):
                st.info("Segment memos not implemented in DB yet.")
                st.session_state[f"open_memo_{i}"] = False

        st.divider()

session.close()
