"""
05_clusters.py — Semantic cluster explorer
==========================================

Review HDBSCAN clusters, accept or revise AI-proposed labels,
and promote clusters to categories in the codebook.
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="Clusters | Thematic Analysis", layout="wide")

st.title("Cluster explorer")
st.caption(
    "Semantic clusters group excerpts by meaning similarity. "
    "Review each cluster, confirm or revise the proposed label, "
    "then promote it to a codebook category."
)

# ── Run clustering ────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("Run clustering")
    min_cluster_size = st.slider("Min cluster size", 3, 20, 5)
    request_labels = st.checkbox("Request AI labels", value=True)
    llm_tier = st.session_state.get("llm_tier", "not configured")
    st.caption(f"AI: {llm_tier}")

    if st.button("Run clustering", type="primary"):
        with st.spinner("Building embeddings and clustering…"):
            st.session_state["clustering_ran"] = True
            st.success("Clustering complete.")

    st.divider()
    st.caption("Only segments with embeddings are clustered. Run ingestion first.")

# ── Demo clusters ─────────────────────────────────────────────────────────────
demo_clusters = [
    {
        "id": "cl-001",
        "label": "Spatial exclusion and institutional gatekeeping",
        "coherence": 0.84,
        "size": 12,
        "is_reviewed": False,
        "excerpts": [
            "Nos quitaron el espacio sin consultarnos. Llevábamos tres años allí.",
            "El centro comunal les pertenecía a ellos institucionalmente, aunque lo construimos nosotros.",
            "Cuando llegaron a cerrar el salón, ni nos avisaron. Llegamos un martes y estaba con llave.",
        ],
    },
    {
        "id": "cl-002",
        "label": "Autonomous community organisation as resistance",
        "coherence": 0.79,
        "size": 9,
        "is_reviewed": False,
        "excerpts": [
            "La comunidad se organizó de todas formas. Empezamos a rotar entre casas.",
            "Crear nuestro propio espacio fue liberador. No dependíamos de nadie.",
            "Eso nos unió más — la necesidad nos hizo más creativos.",
        ],
    },
    {
        "id": "cl-003",
        "label": "Conditionality of institutional support",
        "coherence": 0.71,
        "size": 6,
        "is_reviewed": True,
        "excerpts": [
            "El apoyo siempre venía con condiciones — teníamos que usar su metodología.",
            "Nos ofrecieron recursos pero a cambio de que abandonáramos nuestro enfoque popular.",
        ],
    },
]

# ── Filter ────────────────────────────────────────────────────────────────────
show_reviewed = st.checkbox("Show reviewed clusters", value=False)
visible = [c for c in demo_clusters if not c["is_reviewed"] or show_reviewed]
st.caption(f"{len(visible)} cluster(s) shown")

# ── Cluster cards ─────────────────────────────────────────────────────────────
for cluster in visible:
    reviewed_badge = " ✓" if cluster["is_reviewed"] else ""
    with st.container(border=True):
        col_info, col_actions = st.columns([3, 1])

        with col_info:
            st.markdown(
                f"**{cluster['label']}**{reviewed_badge}  "
                f"— {cluster['size']} segments · coherence {cluster['coherence']:.0%}"
            )

            with st.expander("Representative excerpts"):
                for exc in cluster["excerpts"]:
                    st.markdown(f"> {exc}")

        with col_actions:
            st.markdown("&nbsp;", unsafe_allow_html=True)

            new_label = st.text_input(
                "Category label",
                value=cluster["label"],
                key=f"label_{cluster['id']}",
                label_visibility="collapsed",
            )

            if st.button("Promote to category", key=f"promote_{cluster['id']}"):
                final_label = st.session_state.get(f"label_{cluster['id']}", cluster["label"])
                st.success(f"Promoted as category: '{final_label}'")
                cluster["is_reviewed"] = True

            if st.button("Discard", key=f"discard_{cluster['id']}"):
                st.warning("Cluster discarded.")
                cluster["is_reviewed"] = True

# ── Synthesis button ──────────────────────────────────────────────────────────
st.divider()
col_synth, col_info = st.columns([1, 2])

with col_synth:
    if st.button("Synthesise themes from reviewed categories", type="secondary"):
        llm = st.session_state.get("llm")
        if llm is None:
            st.error("No LLM configured.")
        else:
            with st.spinner("Requesting theme synthesis…"):
                try:
                    result = llm.synthesize_theme(
                        category_labels=[
                            "Spatial exclusion and institutional gatekeeping",
                            "Autonomous community organisation as resistance",
                            "Conditionality of institutional support",
                        ],
                        supporting_excerpts=[e for c in demo_clusters for e in c["excerpts"]],
                        project_context=st.session_state.get("codebook_context", "Community pedagogy research"),
                    )
                    st.subheader("Proposed theme")
                    st.markdown(f"**{result.get('theme_label', 'Unnamed')}**")
                    st.markdown(result.get("narrative", ""))
                    st.caption(f"Evidence: {result.get('evidence_summary', '')}")
                    if result.get("gaps"):
                        st.warning(f"Gaps to investigate: {result['gaps']}")
                except Exception as exc:
                    st.error(f"Synthesis failed: {exc}")

with col_info:
    st.info(
        "Theme synthesis uses your Tier 2 (Claude API) or Tier 1 (Ollama) model. "
        "The result is a draft — you must review, revise, and publish it.",
        icon="ℹ️",
    )
