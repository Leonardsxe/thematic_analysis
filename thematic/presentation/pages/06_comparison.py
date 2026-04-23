"""
06_comparison.py — Cross-source comparison and triangulation
=============================================================

Compare codes and themes across sources, participant groups, and time periods.
Surface contradictions, divergences, and under-represented cases.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Comparison | Thematic Analysis", layout="wide")

st.title("Comparison & triangulation")
st.caption(
    "Compare how codes and themes appear across different sources, speakers, "
    "and participant groups. Surface contradictions for analytical consideration."
)

tab_matrix, tab_contradict, tab_coverage = st.tabs(
    ["Code frequency matrix", "Contradiction analysis", "Coverage gaps"]
)

# ── Code frequency matrix ─────────────────────────────────────────────────────
with tab_matrix:
    st.subheader("Code frequency by source")

    demo_matrix = {
        "Code": [
            "exclusion_from_spaces",
            "community_self_organization",
            "conditional_institutional_support",
        ],
        "Entrevista_Natalia": [7, 5, 3],
        "Entrevista_Lisa": [2, 8, 1],
        "Entrevista_Pedro": [4, 3, 6],
    }

    import pandas as pd
    df = pd.DataFrame(demo_matrix).set_index("Code")
    st.dataframe(df.style.background_gradient(cmap="Greens", axis=None), use_container_width=True)

    st.caption(
        "Values = number of coded segments. "
        "Green intensity = relative frequency. "
        "Empty cells = code not applied in that source."
    )

# ── Contradiction analysis ────────────────────────────────────────────────────
with tab_contradict:
    st.subheader("Contradiction analysis")

    research_question = st.text_input(
        "Research question to analyse",
        value=st.session_state.get("codebook_context", ""),
        placeholder="How do community educators navigate institutional exclusion?",
    )

    selected_sources = st.multiselect(
        "Sources to compare",
        ["Entrevista_Natalia", "Entrevista_Lisa", "Entrevista_Pedro"],
        default=["Entrevista_Natalia", "Entrevista_Lisa"],
    )

    if st.button("Surface contradictions", type="primary"):
        llm = st.session_state.get("llm")
        if llm is None:
            st.error("No LLM configured.")
        elif len(selected_sources) < 2:
            st.warning("Select at least 2 sources to compare.")
        else:
            with st.spinner("Analysing cross-source contradictions…"):
                # Demo excerpts — replace with DB query filtered by source
                demo_by_source = {
                    "Entrevista_Natalia": [
                        "El apoyo institucional siempre venía condicionado a que adoptáramos su metodología.",
                        "La comunidad se organizó de manera autónoma cuando perdimos el espacio.",
                    ],
                    "Entrevista_Lisa": [
                        "La institución fue muy respetuosa de nuestro proceso, nunca nos impusieron nada.",
                        "Tuvimos dificultades para organizarnos solas — necesitábamos el apoyo institucional.",
                    ],
                }
                try:
                    contradictions = llm.surface_contradictions(
                        excerpts_by_source={s: demo_by_source.get(s, []) for s in selected_sources},
                        research_question=research_question,
                    )
                    if not contradictions:
                        st.info("No significant contradictions detected between selected sources.")
                    else:
                        st.subheader(f"{len(contradictions)} contradiction(s) found")
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
                                    st.caption(f"Investigate: {c['investigation_note']}")
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")

# ── Coverage gaps ─────────────────────────────────────────────────────────────
with tab_coverage:
    st.subheader("Coverage analysis")
    st.write(
        "Segments with no applied code ('uncoded') may contain important material "
        "that hasn't been noticed yet, or may be analytically irrelevant."
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Total segments", "284")
    col2.metric("Coded segments", "187")
    col3.metric("Uncoded segments", "97")

    st.progress(187 / 284, text="66% coverage")

    st.subheader("Uncoded segments by source")
    uncoded = pd.DataFrame({
        "Source": ["Entrevista_Natalia", "Entrevista_Lisa", "Entrevista_Pedro"],
        "Uncoded segments": [34, 41, 22],
        "Avg. words": [45, 38, 52],
    })
    st.dataframe(uncoded, use_container_width=True, hide_index=True)

    if st.button("Show longest uncoded segments"):
        st.caption("Longest uncoded segments will appear here once coding data is loaded.")
