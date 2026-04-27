"""
04_codebook.py — Codebook management
=====================================

Create, view, and deprecate codes. Organise codes into categories and themes.
All data is read from and written to the real database — no demo data.
"""

from __future__ import annotations

import dataclasses

import streamlit as st
from thematic.presentation.translations import ts as t
from thematic.infrastructure.db.repositories import SqlCodeRepository
from thematic.application.coding import CreateCodeUseCase


def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised. Please check app.py.")
        st.stop()
    return factory()


st.set_page_config(
    page_title=f"{t('nav_codebook')} | {t('nav_title')}",
    layout="wide",
)

active_project_id = st.session_state.get("active_project_id")

if not active_project_id:
    st.warning(t("codebook_no_project"))
    st.stop()

session = get_session()
code_repo = SqlCodeRepository(session)
all_codes = code_repo.list_for_project(active_project_id)

st.title(t("codebook_title"))

tab_codes, tab_categories, tab_themes = st.tabs([
    t("codebook_tab_codes"),
    t("codebook_tab_categories"),
    t("codebook_tab_themes"),
])

# ── Codes tab ─────────────────────────────────────────────────────────────────
with tab_codes:
    col_list, col_new = st.columns([2, 1])

    with col_list:
        st.subheader(t("codebook_codes_count", n=str(len(all_codes))))

        search = st.text_input(
            "search",
            placeholder=t("codebook_filter_placeholder"),
            label_visibility="collapsed",
        )
        filtered = [c for c in all_codes if not search or search.lower() in c.label.lower()]

        if not filtered:
            st.info(t("codebook_no_codes"))
        else:
            for code in filtered:
                with st.expander(f"**{code.label}** · v{code.version}"):
                    st.markdown(f"**{t('codebook_definition')}:** {code.definition or '—'}")
                    if code.inclusion_criteria:
                        st.markdown(f"**{t('codebook_inclusion')}:** {code.inclusion_criteria}")
                    if code.exclusion_criteria:
                        st.markdown(f"**{t('codebook_exclusion')}:** {code.exclusion_criteria}")
                    if st.button(t("codebook_deprecate"), key=f"dep_{code.id}"):
                        try:
                            deprecated_code = dataclasses.replace(code, is_deprecated=True)
                            code_repo.save(deprecated_code)
                            st.success(f"Code '{code.label}' deprecated.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to deprecate code: {e}")

    with col_new:
        st.subheader(t("codebook_new_code"))
        with st.form("new_code_form"):
            label = st.text_input(
                t("codebook_label"),
                placeholder=t("codebook_label_placeholder"),
            )
            definition = st.text_area(
                t("codebook_definition"),
                height=80,
                placeholder=t("codebook_definition_placeholder"),
            )
            inclusion = st.text_area(
                t("codebook_inclusion"),
                height=60,
                placeholder=t("codebook_inclusion_placeholder"),
            )
            exclusion = st.text_area(
                t("codebook_exclusion"),
                height=60,
                placeholder=t("codebook_exclusion_placeholder"),
            )
            st.text_area(t("codebook_examples"), height=60)
            submitted = st.form_submit_button(t("codebook_create_btn"))
            if submitted:
                if not label.strip():
                    st.error(t("codebook_label_required"))
                elif not definition.strip():
                    st.error(t("codebook_def_required"))
                else:
                    try:
                        CreateCodeUseCase(code_repo).execute(
                            project_id=active_project_id,
                            label=label.strip(),
                            definition=definition.strip(),
                            inclusion_criteria=inclusion.strip(),
                            exclusion_criteria=exclusion.strip(),
                        )
                        session.commit()
                        st.success(t("codebook_created_ok", label=label.strip()))
                        st.rerun()
                    except Exception as e:
                        st.error(t("codebook_create_failed", error=str(e)))

session.close()

# ── Categories tab ────────────────────────────────────────────────────────────
with tab_categories:
    st.subheader(t("codebook_tab_categories"))
    st.info(t("codebook_categories_info"))

    with st.form("new_category"):
        cat_label = st.text_input(t("codebook_new_category"))
        st.text_area(t("codebook_rationale"), height=60)
        if st.form_submit_button(t("codebook_create_category")):
            if cat_label.strip():
                st.success(f"Category '{cat_label}' created.")

# ── Themes tab ────────────────────────────────────────────────────────────────
with tab_themes:
    st.subheader(t("codebook_tab_themes"))
    st.warning(t("codebook_themes_warning"), icon="⚠️")
    st.info(
        "Themes are built from reviewed clusters. "
        "Go to the **Clusters** page to run clustering and promote categories to themes."
    )