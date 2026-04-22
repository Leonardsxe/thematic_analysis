"""
07_export.py — Export centre
==============================

Export versioned research artefacts:
  - Evidence matrix (.csv / .xlsx)
  - Codebook (.json / .md)
  - Audit trail (.json)
  - Theme summaries (.md / .txt)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Export | Thematic Analysis", layout="wide")

st.title("Export centre")
st.caption(
    "All exports include full provenance: source identifier, segment location, "
    "analyst, model run, and timestamp."
)

tab_matrix, tab_codebook, tab_audit = st.tabs(
    ["Evidence matrix", "Codebook", "Audit trail"]
)

# ── Evidence matrix ───────────────────────────────────────────────────────────
with tab_matrix:
    st.subheader("Evidence matrix")
    st.write(
        "The evidence matrix cross-references codes against sources. "
        "Each cell contains the excerpts where that code appears in that source."
    )

    col_fmt, col_filter = st.columns(2)
    with col_fmt:
        fmt = st.selectbox("Format", ["CSV", "Excel (.xlsx)", "Markdown"])
    with col_filter:
        speaker_filter = st.multiselect(
            "Speaker filter",
            ["INTERVIEWEE", "INTERVIEWER", "UNKNOWN"],
            default=["INTERVIEWEE"],
        )

    include_ai = st.checkbox("Include AI-assisted codings", value=True)
    include_note = st.checkbox("Include analyst notes", value=True)

    if st.button("Generate evidence matrix"):
        with st.spinner("Building matrix…"):
            # Placeholder — replace with ExportEvidenceMatrixUseCase
            demo_data = [
                {
                    "Code": "exclusion_from_spaces",
                    "Source": "Entrevista_Natalia",
                    "Speaker": "INTERVIEWEE",
                    "Time": "45s",
                    "Excerpt": "Nos quitaron el espacio sin consultarnos…",
                    "Analyst": "analyst",
                    "AI": False,
                },
                {
                    "Code": "community_self_organization",
                    "Source": "Entrevista_Natalia",
                    "Speaker": "INTERVIEWEE",
                    "Time": "123s",
                    "Excerpt": "La comunidad se organizó de todas formas…",
                    "Analyst": "analyst",
                    "AI": True,
                },
            ]
            import pandas as pd  # type: ignore[import]
            df = pd.DataFrame(demo_data)
            st.dataframe(df, use_container_width=True)

            if fmt == "CSV":
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "Download CSV",
                    data=csv,
                    file_name=f"evidence_matrix_{datetime.now(tz=timezone.utc).strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                )

# ── Codebook ──────────────────────────────────────────────────────────────────
with tab_codebook:
    st.subheader("Versioned codebook")
    st.write(
        "Export the current codebook with all code definitions, inclusion/exclusion "
        "criteria, examples, and category/theme assignments."
    )

    codebook_fmt = st.selectbox(
        "Format",
        ["JSON (machine-readable)", "Markdown (human-readable)"],
        key="codebook_fmt",
    )

    if st.button("Export codebook"):
        demo_codebook = {
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
            "schema_version": "1.0",
            "codes": [
                {
                    "label": "exclusion_from_spaces",
                    "definition": "Participant describes being removed from or denied access to a community or public space.",
                    "inclusion_criteria": "Must reference a physical space. Must describe removal or denial.",
                    "exclusion_criteria": "Symbolic or metaphorical exclusion without a physical dimension.",
                    "examples": ["Nos quitaron el espacio sin consultarnos…"],
                    "version": 1,
                }
            ],
        }
        codebook_json = json.dumps(demo_codebook, ensure_ascii=False, indent=2)
        st.download_button(
            "Download codebook",
            data=codebook_json.encode("utf-8"),
            file_name="codebook.json",
            mime="application/json",
        )
        with st.expander("Preview"):
            st.json(demo_codebook)

# ── Audit trail ───────────────────────────────────────────────────────────────
with tab_audit:
    st.subheader("Audit trail")
    st.write(
        "Full log of every coding decision, AI model run, suggestion acceptance or "
        "rejection, and codebook modification — with analyst, timestamp, and model version."
    )

    date_range = st.date_input("Date range", value=[], key="audit_dates")

    if st.button("Export audit trail"):
        demo_audit = [
            {
                "event": "coding_decision",
                "segment_id": "seg-001",
                "code": "exclusion_from_spaces",
                "analyst": "analyst",
                "is_ai": False,
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
            {
                "event": "ai_suggestion_accepted",
                "segment_id": "seg-002",
                "code": "community_self_organization",
                "model": "mistral:7b",
                "model_run_id": "run-abc",
                "analyst": "analyst",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        ]
        audit_json = json.dumps(demo_audit, ensure_ascii=False, indent=2)
        st.download_button(
            "Download audit trail",
            data=audit_json.encode("utf-8"),
            file_name="audit_trail.json",
            mime="application/json",
        )
        with st.expander("Preview"):
            st.json(demo_audit)
