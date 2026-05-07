"""
07_export.py — Export centre
thematic/presentation/pages/07_export.py
==============================

Exports versioned research artefacts using the real application use cases.
No demo data — all content is built from the live database.
"""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from thematic.presentation.translations import ts as t
from thematic.infrastructure.db.repositories import (
    SqlCodeRepository,
    SqlCodingDecisionRepository,
    SqlModelRunRepository,
    SqlSegmentRepository,
    SqlSourceRepository,
)
from thematic.presentation.shared_sidebar import render_sidebar
from thematic.application.export import (
    BuildEvidenceMatrixUseCase,
    ExportEvidenceMatrixCsvUseCase,
    ExportCodebookJsonUseCase,
    ExportCodebookMarkdownUseCase,
    ExportAuditTrailUseCase,
)


def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised.")
        st.stop()
    return factory()


render_sidebar()
st.set_page_config(
    page_title=f"{t('nav_export')} | {t('nav_title')}",
    layout="wide",
)

active_project_id = st.session_state.get("active_project_id")

if not active_project_id:
    st.warning(t("export_no_project"))
    st.stop()

st.title(t("export_title"))
st.caption(t("export_caption"))

tab_matrix, tab_codebook, tab_audit = st.tabs([
    t("export_tab_matrix"),
    t("export_tab_codebook"),
    t("export_tab_audit"),
])

# ── Evidence matrix ───────────────────────────────────────────────────────────
with tab_matrix:
    st.subheader(t("export_matrix_title"))
    st.write(t("export_matrix_body"))

    col_fmt, col_filter = st.columns(2)
    with col_fmt:
        fmt = st.selectbox(t("export_format"), ["CSV", "Excel (.xlsx)"])
    with col_filter:
        speaker_filter = st.multiselect(
            t("export_speaker_filter"),
            ["INTERVIEWEE", "INTERVIEWER", "UNKNOWN"],
            default=["INTERVIEWEE"],
        )

    include_ai    = st.checkbox(t("export_include_ai"), value=True)
    st.checkbox(t("export_include_notes"), value=True)

    if st.button(t("export_generate_btn")):
        with st.spinner(t("export_generating")):
            try:
                session = get_session()
                matrix = BuildEvidenceMatrixUseCase(
                    decision_repo=SqlCodingDecisionRepository(session),
                    segment_repo=SqlSegmentRepository(session),
                    code_repo=SqlCodeRepository(session),
                    source_repo=SqlSourceRepository(session),
                ).execute(
                    active_project_id,
                    speaker_filter=speaker_filter or None,
                    include_ai=include_ai,
                )
                session.close()

                if not matrix.rows:
                    st.info(t("export_no_data"))
                else:
                    import pandas as pd
                    df = pd.DataFrame([
                        {
                            "Code": r.code_label,
                            "Source": r.source_title,
                            "Speaker": r.speaker,
                            "Start (s)": f"{r.start_s:.1f}" if r.start_s is not None else "",
                            "Excerpt": r.excerpt,
                            "Analyst": r.analyst,
                            "AI": "yes" if r.is_ai else "no",
                        }
                        for r in matrix.rows
                    ])
                    st.dataframe(df, width="stretch")

                    csv_str = ExportEvidenceMatrixCsvUseCase().execute(matrix)
                    ts_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
                    st.download_button(
                        t("export_download_csv"),
                        data=csv_str.encode("utf-8"),
                        file_name=f"evidence_matrix_{ts_str}.csv",
                        mime="text/csv",
                    )
            except Exception as exc:
                st.error(t("export_failed", error=str(exc)))

# ── Codebook ──────────────────────────────────────────────────────────────────
with tab_codebook:
    st.subheader(t("export_codebook_title"))
    st.write(t("export_codebook_body"))

    st.selectbox(t("export_codebook_fmt"), ["Markdown (.md) — Human readable", "JSON — Machine readable"], key="codebook_fmt")

    if st.button(t("export_codebook_btn")):
        try:
            session = get_session()
            ts_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
            fmt = st.session_state.get("codebook_fmt", "")

            if "Markdown" in fmt:
                payload = ExportCodebookMarkdownUseCase(
                    SqlCodeRepository(session)
                ).execute(active_project_id)
                session.close()
                st.download_button(
                    "⬇️ Download Codebook (.md)",
                    data=payload.encode("utf-8"),
                    file_name=f"codebook_{ts_str}.md",
                    mime="text/markdown",
                )
                with st.expander(t("export_preview")):
                    st.markdown(payload)
            else:
                payload = ExportCodebookJsonUseCase(
                    SqlCodeRepository(session)
                ).execute(active_project_id)
                session.close()
                import json as _json
                st.download_button(
                    "⬇️ Download Codebook (.json)",
                    data=payload.encode("utf-8"),
                    file_name=f"codebook_{ts_str}.json",
                    mime="application/json",
                )
                with st.expander(t("export_preview")):
                    st.json(_json.loads(payload))
        except Exception as exc:
            st.error(t("export_failed", error=str(exc)))

# ── Audit trail ───────────────────────────────────────────────────────────────
with tab_audit:
    st.subheader(t("export_audit_title"))
    st.write(t("export_audit_body"))

    st.date_input(t("export_audit_dates"), value=[], key="audit_dates")

    if st.button(t("export_audit_btn")):
        try:
            session = get_session()
            payload = ExportAuditTrailUseCase(
                decision_repo=SqlCodingDecisionRepository(session),
                run_repo=SqlModelRunRepository(session),
            ).execute(active_project_id)
            session.close()

            import json
            preview = json.loads(payload)
            ts_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
            st.download_button(
                t("export_audit_btn"),
                data=payload.encode("utf-8"),
                file_name=f"audit_trail_{ts_str}.json",
                mime="application/json",
            )
            with st.expander(t("export_preview")):
                st.json(preview)
        except Exception as exc:
            st.error(t("export_failed", error=str(exc)))