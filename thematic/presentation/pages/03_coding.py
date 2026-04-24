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
from thematic.presentation.translations import t
from thematic.infrastructure.db.repositories import (
    SqlSourceRepository,
    SqlSegmentRepository,
    SqlCodeRepository,
    SqlCodingDecisionRepository,
)
from thematic.application.coding import ApplyCodeUseCase, SuggestCodesUseCase

# ── Infrastructure ────────────────────────────────────────────────────────────
def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised. Please check app.py.")
        st.stop()
    return factory()

st.set_page_config(page_title=f"{t('nav_coding')} | {t('nav_title')}", layout="wide")


def _get_llm():
    return st.session_state.get("llm")


def _get_db():
    factory = st.session_state.get("db_session_factory")
    return factory() if factory else None


def render_segment_card(seg, codes: list[str], session) -> None:
    """Render one segment with its coding controls."""
    speaker = seg.speaker
    start = seg.start_s
    text = seg.text

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
            key=f"codes_{seg.id}",
            label_visibility="collapsed",
            placeholder="Select codes to apply…",
        )
        if selected and st.button("Apply", key=f"apply_{seg.id}"):
            try:
                apply_use_case = ApplyCodeUseCase(
                    SqlCodingDecisionRepository(session),
                    SqlCodeRepository(session)
                )
                for code_label in selected:
                    apply_use_case.execute(
                        segment_id=seg.id,
                        code_label=code_label,
                        analyst_id=st.session_state.get("analyst", "analyst")
                    )
                session.commit()
                st.success(f"Applied: {', '.join(selected)}")
            except Exception as e:
                st.error(f"Failed to apply codes: {e}")

    with col_ai:
        if st.button("AI suggest", key=f"ai_{seg.id}"):
            llm = _get_llm()
            if llm is None:
                st.error("No LLM configured.")
            else:
                with st.spinner("Requesting suggestions…"):
                    try:
                        suggest_use_case = SuggestCodesUseCase(
                            llm_service=llm,
                            code_repo=SqlCodeRepository(session)
                        )
                        suggestions = suggest_use_case.execute(
                            segment_text=text,
                            project_id=st.session_state.get("active_project_id", ""),
                            context=st.session_state.get("codebook_context", "")
                        )
                        st.session_state[f"suggestions_{seg.id}"] = suggestions
                    except Exception as exc:
                        st.error(f"LLM error: {exc}")

    with col_memo:
        if st.button("Memo", key=f"memo_{seg.id}"):
            st.session_state[f"show_memo_{seg.id}"] = True

    # ── AI suggestions ────────────────────────────────────────────────────────
    suggestions = st.session_state.get(f"suggestions_{seg.id}", [])
    if suggestions:
        st.markdown("**AI suggestions** (all pending — review each one)")
        for i, s in enumerate(suggestions):
            with st.container(border=True):
                confidence = s.confidence
                label = s.code_label
                justification = s.justification
                is_new = s.is_new_code

                badge = " ✦ new code" if is_new else ""
                st.markdown(
                    f"**{label}**{badge} — confidence: {confidence:.0%}"
                )
                st.caption(justification)
                col_a, col_r = st.columns(2)
                with col_a:
                    if st.button("Accept", key=f"accept_{seg.id}_{i}"):
                        apply_use_case = ApplyCodeUseCase(
                            SqlCodingDecisionRepository(session),
                            SqlCodeRepository(session)
                        )
                        apply_use_case.execute(
                            segment_id=seg.id,
                            code_label=label,
                            analyst_id=st.session_state.get("analyst", "analyst")
                        )
                        session.commit()
                        st.success(f"Accepted '{label}'.")
                        suggestions.pop(i)
                        st.rerun()
                with col_r:
                    if st.button("Reject", key=f"reject_{seg.id}_{i}"):
                        suggestions.pop(i)
                        st.rerun()

    # ── Memo input ────────────────────────────────────────────────────────────
    if st.session_state.get(f"show_memo_{seg.id}"):
        memo_text = st.text_area("Memo", key=f"memo_text_{seg.id}", height=80)
        if st.button("Save memo", key=f"save_memo_{seg.id}"):
            st.info("Memos not implemented in DB yet.")
            st.session_state[f"show_memo_{seg.id}"] = False

    st.divider()


# ─────────────────────────────────────────────
#  Main page
# ─────────────────────────────────────────────

active_project_id = st.session_state.get("active_project_id")
active_corpus_id = st.session_state.get("active_corpus_id")

if not active_project_id or not active_corpus_id:
    st.warning("Please select a project and corpus first in the 'Corpus' page.")
    st.stop()

session = get_session()
source_repo = SqlSourceRepository(session)
segment_repo = SqlSegmentRepository(session)
code_repo = SqlCodeRepository(session)

st.title(t('nav_coding'))

# Sidebar controls
with st.sidebar:
    st.subheader("Session settings")
    analyst = st.text_input("Analyst name", value=st.session_state.get("analyst", "analyst"))
    st.session_state["analyst"] = analyst

    codebook_context = st.text_area(
        "Research question / context",
        value=st.session_state.get("codebook_context", ""),
        help="Passed to the AI model with every suggestion request.",
        height=80,
    )
    st.session_state["codebook_context"] = codebook_context

    st.divider()
    st.caption("Source filter")
    
    all_sources = source_repo.list_for_corpus(active_corpus_id)
    source_titles = [s.title for s in all_sources]
    
    if not source_titles:
        st.info("No sources found in this corpus.")
        session.close()
        st.stop()

    selected_title = st.selectbox(t('nav_corpus'), source_titles)
    active_source = next(s for s in all_sources if s.title == selected_title)

    speaker_filter = st.selectbox(
        "Show speaker",
        ["INTERVIEWEE only", "All speakers"],
        index=0,
    )

# Load real data
codes = code_repo.list_for_project(active_project_id)
code_labels = [c.label for c in codes]

segments = segment_repo.list_for_source(active_source.id)
if speaker_filter == "INTERVIEWEE only":
    visible = [s for s in segments if s.speaker == "INTERVIEWEE"]
else:
    visible = segments

col_main, col_similar = st.columns([3, 1])

with col_main:
    st.subheader(f"Segments ({len(visible)} shown)")
    for seg in visible:
        render_segment_card(seg, code_labels, session)

with col_similar:
    st.subheader("Similar segments")
    query = st.text_input("Search by text", placeholder="Type a concept…")
    if query and st.button("Find similar"):
        settings = st.session_state.get("settings")
        embedder = ChromaEmbeddingService(
            persist_path=settings.chroma_path,
            model_name=settings.embedding_model,
            device=settings.embedding_device,
        )
        with st.spinner("Searching…"):
            try:
                results = embedder.find_similar(query, top_k=5, project_id=active_project_id)
                if not results:
                    st.info("No similar segments found.")
                for seg_id, score in results:
                    seg = segment_repo.get(seg_id)
                    if seg:
                        st.markdown(f"**{seg.speaker}** ({score:.1%})")
                        st.caption(seg.text[:200] + "…")
                        st.divider()
            except Exception as e:
                st.error(f"Search failed: {e}")

session.close()
