"""
06_comparison.py — Cross-source comparison and triangulation
=============================================================

Builds the evidence matrix and coverage stats from real DB data.
Contradiction analysis passes actual DB excerpts to the LLM.
No demo data.
"""

from __future__ import annotations

from collections import defaultdict

import pandas as pd
import streamlit as st

from thematic.presentation.translations import ts as t
from thematic.infrastructure.db.repositories import (
    SqlCodeRepository,
    SqlCodingDecisionRepository,
    SqlSegmentRepository,
    SqlSourceRepository,
)


def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised.")
        st.stop()
    return factory()


st.set_page_config(
    page_title=f"{t('nav_comparison')} | {t('nav_title')}",
    layout="wide",
)

active_project_id = st.session_state.get("active_project_id")
active_corpus_id  = st.session_state.get("active_corpus_id")

if not active_project_id or not active_corpus_id:
    st.warning(t("comparison_no_project"))
    st.stop()

st.title(t("comparison_title"))
st.caption(t("comparison_caption"))

tab_matrix, tab_contradict, tab_coverage = st.tabs([
    t("comparison_tab_matrix"),
    t("comparison_tab_contradict"),
    t("comparison_tab_coverage"),
])

# ── Load shared data ──────────────────────────────────────────────────────────
session     = get_session()
codes       = SqlCodeRepository(session).list_for_project(active_project_id)
sources     = SqlSourceRepository(session).list_for_corpus(active_corpus_id)
all_segs    = {
    seg.id: seg
    for src in sources
    for seg in SqlSegmentRepository(session).list_for_source(src.id)
}
all_decisions = SqlCodingDecisionRepository(session).list_for_project(active_project_id)
session.close()

code_map   = {c.id: c.label for c in codes}
source_map = {s.id: s.title or s.id for s in sources}

# Build pivot: code_label → source_title → count
pivot: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
for dec in all_decisions:
    seg = all_segs.get(dec.segment_id)
    if seg and seg.source_id in source_map:
        pivot[code_map.get(dec.code_id, "?")][source_map[seg.source_id]] += 1

# ── Code frequency matrix ─────────────────────────────────────────────────────
with tab_matrix:
    st.subheader(t("comparison_matrix_title"))

    if not codes or not sources:
        st.info("No codes or sources found. Import transcripts and apply codes first.")
    else:
        source_titles = [source_map[s.id] for s in sources]
        rows = []
        for code in codes:
            row = {"Code": code.label}
            for title in source_titles:
                row[title] = pivot[code.label].get(title, 0)
            rows.append(row)
        df = pd.DataFrame(rows).set_index("Code")
        st.dataframe(
            df.style.background_gradient(cmap="Greens", axis=None),
            width="stretch",
        )
        st.caption(t("comparison_matrix_caption"))

# ── Contradiction analysis ────────────────────────────────────────────────────
with tab_contradict:
    st.subheader(t("comparison_tab_contradict"))

    research_question = st.text_input(
        t("comparison_rq_label"),
        value=st.session_state.get("codebook_context", ""),
        placeholder=t("comparison_rq_placeholder"),
    )

    source_titles_list = [source_map[s.id] for s in sources]
    selected_titles = st.multiselect(
        t("comparison_sources_label"),
        source_titles_list,
        default=source_titles_list[:2] if len(source_titles_list) >= 2 else source_titles_list,
    )

    if st.button(t("comparison_surface_btn"), type="primary"):
        llm = st.session_state.get("llm")
        if llm is None:
            st.error(t("comparison_no_llm"))
        elif len(selected_titles) < 2:
            st.warning(t("comparison_need_2_sources"))
        else:
            # Build excerpts_by_source from real DB data (INTERVIEWEE only)
            title_to_id = {source_map[s.id]: s.id for s in sources}
            excerpts_by_source: dict[str, list[str]] = defaultdict(list)
            for dec in all_decisions:
                seg = all_segs.get(dec.segment_id)
                if seg and seg.speaker == "INTERVIEWEE":
                    title = source_map.get(seg.source_id, "")
                    if title in selected_titles:
                        excerpts_by_source[title].append(seg.text[:400])

            with st.spinner(t("comparison_analysing")):
                try:
                    contradictions = llm.surface_contradictions(
                        excerpts_by_source={t_: excerpts_by_source.get(t_, []) for t_ in selected_titles},
                        research_question=research_question,
                    )
                    if not contradictions:
                        st.info(t("comparison_no_contradict"))
                    else:
                        st.subheader(t("comparison_found", n=str(len(contradictions))))
                        for c in contradictions:
                            with st.container(border=True):
                                col_a, col_b = st.columns(2)
                                with col_a:
                                    st.markdown(f"**{c.get('source_a', '')}**")
                                    st.markdown(f"> {c.get('excerpt_a', '')}")
                                with col_b:
                                    st.markdown(f"**{c.get('source_b', '')}**")
                                    st.markdown(f"> {c.get('excerpt_b', '')}")
                                st.warning(c.get("contradiction_note", ""))
                                if c.get("investigation_note"):
                                    st.caption(t("comparison_investigate", note=c["investigation_note"]))
                except Exception as exc:
                    st.error(t("comparison_failed", error=str(exc)))

# ── Coverage gaps ─────────────────────────────────────────────────────────────
with tab_coverage:
    st.subheader(t("comparison_coverage_title"))
    st.write(t("comparison_coverage_body"))

    coded_ids   = {dec.segment_id for dec in all_decisions}
    total_segs  = len(all_segs)
    coded_segs  = len(coded_ids & all_segs.keys())
    uncoded_segs = total_segs - coded_segs

    col1, col2, col3 = st.columns(3)
    col1.metric(t("comparison_total_segs"),  str(total_segs))
    col2.metric(t("comparison_coded_segs"),  str(coded_segs))
    col3.metric(t("comparison_uncoded_segs"), str(uncoded_segs))

    if total_segs > 0:
        pct = coded_segs / total_segs
        st.progress(pct, text=f"{pct:.0%} coverage")

    st.subheader(t("comparison_uncoded_title"))
    uncoded_rows = []
    for src in sources:
        src_segs  = [s for s in all_segs.values() if s.source_id == src.id]
        src_uncoded = [s for s in src_segs if s.id not in coded_ids]
        avg_words = (
            sum(len(s.text.split()) for s in src_uncoded) / len(src_uncoded)
            if src_uncoded else 0
        )
        uncoded_rows.append({
            "Source": source_map[src.id],
            t("comparison_uncoded_segs"): len(src_uncoded),
            "Avg. words": round(avg_words),
        })

    if uncoded_rows:
        st.dataframe(pd.DataFrame(uncoded_rows), width="stretch", hide_index=True)

    if st.button(t("comparison_show_longest")):
        uncoded_list = sorted(
            [s for s in all_segs.values() if s.id not in coded_ids],
            key=lambda s: len(s.text),
            reverse=True,
        )[:5]
        for seg in uncoded_list:
            src_title = source_map.get(seg.source_id, "?")
            with st.container(border=True):
                st.caption(f"{src_title} · {seg.speaker} · {len(seg.text.split())} words")
                st.markdown(f"> {seg.text[:300]}{'…' if len(seg.text) > 300 else ''}")