"""
05_clusters.py — Semantic cluster explorer
==========================================

Runs HDBSCAN clustering on embedded segments, displays results from the DB,
and lets analysts promote clusters to codebook categories.
No demo data — all reads and writes go through the real repositories.
"""

from __future__ import annotations

import streamlit as st
from thematic.presentation.translations import ts as t
from thematic.infrastructure.db.repositories import (
    SqlSegmentRepository,
    SqlClusterRepository,
    SqlModelRunRepository,
)
from thematic.application.clustering import RunClusteringUseCase, ClusteringConfig


def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised.")
        st.stop()
    return factory()


st.set_page_config(
    page_title=f"{t('nav_clusters')} | {t('nav_title')}",
    layout="wide",
)

active_project_id = st.session_state.get("active_project_id")
active_corpus_id  = st.session_state.get("active_corpus_id")

if not active_project_id or not active_corpus_id:
    st.warning(t("clusters_no_project"))
    st.stop()

st.title(t("clusters_title"))
st.caption(t("clusters_caption"))

# ── Sidebar — run clustering ──────────────────────────────────────────────────
with st.sidebar:
    st.subheader(t("clusters_run_title"))
    min_cluster_size = st.slider(t("clusters_min_size"), 3, 20, 5)
    request_labels   = st.checkbox(t("clusters_ai_labels"), value=True)
    llm_tier = st.session_state.get("llm_tier", "not configured")
    st.caption(f"AI: {llm_tier}")

    if st.button(t("clusters_run_btn"), type="primary"):
        chroma = st.session_state.get("chroma_service")
        if chroma is None:
            st.error(t("clusters_no_segments"))
        else:
            with st.spinner(t("clusters_running")):
                try:
                    session = get_session()
                    llm = st.session_state.get("llm") if request_labels else None
                    use_case = RunClusteringUseCase(
                        embedding_service=chroma,
                        segment_repo=SqlSegmentRepository(session),
                        cluster_repo=SqlClusterRepository(session),
                        run_repo=SqlModelRunRepository(session),
                        llm_service=llm,
                        config=ClusteringConfig(min_cluster_size=min_cluster_size),
                    )
                    clusters = use_case.execute(project_id=active_project_id)
                    session.close()
                    if clusters:
                        st.success(t("clusters_done"))
                        st.rerun()
                    else:
                        st.warning(t("clusters_no_segments"))
                except Exception as exc:
                    st.error(str(exc))

    st.divider()
    st.caption(t("clusters_embed_note"))

# ── Load clusters from DB ─────────────────────────────────────────────────────
session = get_session()
all_clusters = SqlClusterRepository(session).list_for_project(active_project_id)
session.close()

show_reviewed = st.checkbox(t("clusters_show_reviewed"), value=False)
visible = [c for c in all_clusters if not c.is_reviewed or show_reviewed]
st.caption(t("clusters_shown", n=str(len(visible))))

if not visible:
    st.info(t("clusters_no_segments"))
else:
    for cluster in visible:
        reviewed_badge = " ✓" if cluster.is_reviewed else ""
        with st.container(border=True):
            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(
                    f"**{cluster.label or 'Unlabelled'}**{reviewed_badge}  "
                    f"— {cluster.size} segments · coherence {cluster.coherence:.0%}"
                )
                with st.expander(t("clusters_excerpts")):
                    for exc in (cluster.excerpts or [])[:3]:
                        st.markdown(f"> {exc}")

            with col_actions:
                st.markdown("&nbsp;", unsafe_allow_html=True)
                new_label = st.text_input(
                    t("clusters_category_label"),
                    value=cluster.label or "",
                    key=f"label_{cluster.id}",
                    label_visibility="collapsed",
                )
                if st.button(t("clusters_promote"), key=f"promote_{cluster.id}"):
                    final_label = st.session_state.get(f"label_{cluster.id}", cluster.label)
                    st.success(t("clusters_promoted_ok", label=final_label))
                if st.button(t("clusters_discard"), key=f"discard_{cluster.id}"):
                    st.warning(t("clusters_discard"))

# ── Theme synthesis ───────────────────────────────────────────────────────────
st.divider()
col_synth, col_info_box = st.columns([1, 2])

reviewed_labels = [c.label for c in all_clusters if c.is_reviewed and c.label]

with col_synth:
    if st.button(t("clusters_synthesise"), type="secondary"):
        llm = st.session_state.get("llm")
        if llm is None:
            st.error(t("clusters_no_llm"))
        elif not reviewed_labels:
            st.warning("No reviewed clusters to synthesise. Review some clusters first.")
        else:
            reviewed_excerpts = [
                exc
                for c in all_clusters
                if c.is_reviewed
                for exc in (c.excerpts or [])
            ]
            with st.spinner(t("clusters_synthesising")):
                try:
                    result = llm.synthesize_theme(
                        category_labels=reviewed_labels,
                        supporting_excerpts=reviewed_excerpts,
                        project_context=st.session_state.get(
                            "codebook_context", "Community pedagogy research"
                        ),
                    )
                    st.subheader(t("clusters_proposed_theme"))
                    st.markdown(f"**{result.get('theme_label', 'Unnamed')}**")
                    st.markdown(result.get("narrative", ""))
                    st.caption(f"Evidence: {result.get('evidence_summary', '')}")
                    if result.get("gaps"):
                        st.warning(t("clusters_gaps", gaps=result["gaps"]))
                except Exception as exc:
                    st.error(t("clusters_synth_failed", error=str(exc)))

with col_info_box:
    st.info(t("clusters_synthesis_info"), icon="ℹ️")