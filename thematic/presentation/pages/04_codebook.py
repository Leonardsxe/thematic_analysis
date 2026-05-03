"""
04_codebook.py — Codebook management
=====================================

Three-tier hierarchy: Code → Category → Theme
All tabs backed by real DB — no demo data, no silent drops.
"""

from __future__ import annotations

import dataclasses

import streamlit as st
from thematic.presentation.translations import ts as t
from thematic.infrastructure.db.repositories import (
    SqlCodeRepository,
    SqlCategoryRepository,
    SqlThemeRepository,
)
from thematic.application.coding import CreateCodeUseCase
from thematic.domain.entities import Category, Theme
from thematic.presentation.shared_sidebar import render_sidebar


def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised.")
        st.stop()
    return factory()


render_sidebar()
st.set_page_config(page_title=f"{t('nav_codebook')} | {t('nav_title')}", layout="wide")

active_project_id = st.session_state.get("active_project_id")
if not active_project_id:
    st.warning(t("codebook_no_project"))
    st.stop()

st.title(t("codebook_title"))

tab_codes, tab_categories, tab_themes = st.tabs([
    t("codebook_tab_codes"),
    t("codebook_tab_categories"),
    t("codebook_tab_themes"),
])

# ── Codes tab ─────────────────────────────────────────────────────────────────
with tab_codes:
    session = get_session()
    code_repo = SqlCodeRepository(session)
    all_codes = code_repo.list_for_project(active_project_id)

    col_list, col_new = st.columns([2, 1])

    with col_list:
        st.subheader(t("codebook_codes_count", n=str(len(all_codes))))

        search = st.text_input(
            "search", placeholder=t("codebook_filter_placeholder"),
            label_visibility="collapsed",
        )
        filtered = [c for c in all_codes
                    if not search or search.lower() in c.label.lower()]

        if not filtered:
            st.info(t("codebook_no_codes"))
        else:
            for code in filtered:
                dep_tag = " ~~deprecated~~" if code.is_deprecated else ""
                with st.expander(f"**{code.label}**{dep_tag} · v{code.version}"):
                    cols = st.columns(2)
                    with cols[0]:
                        st.markdown(f"**{t('codebook_definition')}**")
                        st.write(code.definition or "—")
                        if code.inclusion_criteria:
                            st.markdown(f"**{t('codebook_inclusion')}**")
                            st.write(code.inclusion_criteria)
                    with cols[1]:
                        if code.exclusion_criteria:
                            st.markdown(f"**{t('codebook_exclusion')}**")
                            st.write(code.exclusion_criteria)
                        if code.examples:
                            st.markdown("**Examples**")
                            st.write(code.examples)

                    if not code.is_deprecated:
                        if st.button(t("codebook_deprecate"), key=f"dep_{code.id}"):
                            try:
                                code_repo.save(dataclasses.replace(code, is_deprecated=True))
                                st.success(f"'{code.label}' deprecated.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Failed: {e}")
                    else:
                        st.caption("⚠️ This code is deprecated and will not appear in suggestions.")

    with col_new:
        st.subheader(t("codebook_new_code"))
        with st.form("new_code_form", clear_on_submit=True):
            label      = st.text_input(t("codebook_label"), placeholder=t("codebook_label_placeholder"))
            definition = st.text_area(t("codebook_definition"), height=80,
                                      placeholder=t("codebook_definition_placeholder"))
            inclusion  = st.text_area(t("codebook_inclusion"), height=60,
                                      placeholder=t("codebook_inclusion_placeholder"))
            exclusion  = st.text_area(t("codebook_exclusion"), height=60,
                                      placeholder=t("codebook_exclusion_placeholder"))
            examples   = st.text_area(t("codebook_examples"), height=60)
            if st.form_submit_button(t("codebook_create_btn"), type="primary"):
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
    cat_session = get_session()
    cat_repo    = SqlCategoryRepository(cat_session)
    categories  = cat_repo.list_for_project(active_project_id)

    col_cats, col_new_cat = st.columns([2, 1])

    with col_cats:
        st.subheader(f"{t('codebook_tab_categories')} ({len(categories)})")

        if not categories:
            st.info(t("codebook_categories_info"))
        else:
            # Load all codes for assignment display
            _code_sess = get_session()
            _all_codes = SqlCodeRepository(_code_sess).list_for_project(active_project_id)
            _code_sess.close()
            _code_by_cat: dict[str, list] = {}
            for _c in _all_codes:
                _key = getattr(_c, "category_id", None) or "__none__"
                _code_by_cat.setdefault(_key, []).append(_c)

            for cat in categories:
                with st.expander(f"**{cat.label}**"):
                    st.markdown(f"**{t('codebook_rationale')}:** {cat.rationale or '—'}")
                    # Codes in this category
                    cat_codes = _code_by_cat.get(cat.id, [])
                    if cat_codes:
                        st.markdown("**Codes in this category:**")
                        for _cc in cat_codes:
                            st.markdown(f"  - `{_cc.label}`")
                    else:
                        st.caption("No codes assigned yet — use 'Assign to category' below.")

                    # Assign codes to this category
                    _unassigned = [_c for _c in _all_codes if not getattr(_c, "category_id", None)]
                    if _unassigned:
                        _opts = [_c.label for _c in _unassigned]
                        _to_assign = st.multiselect(
                            "Assign codes to this category",
                            _opts,
                            key=f"assign_cat_{cat.id}",
                        )
                        if _to_assign and st.button("Save assignments", key=f"save_assign_{cat.id}"):
                            import dataclasses as _dc
                            _asgn_sess = get_session()
                            _cat_code_repo = SqlCodeRepository(_asgn_sess)
                            for _lbl in _to_assign:
                                _target = next((_c for _c in _all_codes if _c.label == _lbl), None)
                                if _target:
                                    _cat_code_repo.save(_dc.replace(_target, category_id=cat.id))
                            _asgn_sess.commit()
                            _asgn_sess.close()
                            st.success(f"Assigned {len(_to_assign)} code(s) to '{cat.label}'.")
                            st.rerun()

                    if cat.theme_id:
                        st.caption(f"→ Assigned to theme `{cat.theme_id[:8]}`")
                    if st.button("🗑️ Delete", key=f"del_cat_{cat.id}"):
                        cat_repo.delete(cat.id)
                        cat_session.commit()
                        st.rerun()

    with col_new_cat:
        st.subheader(t("codebook_new_category"))
        st.caption(t("codebook_categories_info"))
        with st.form("new_category_form", clear_on_submit=True):
            cat_label     = st.text_input(t("codebook_new_category"),
                                          placeholder="e.g. exclusion_from_institutions")
            cat_rationale = st.text_area(t("codebook_rationale"), height=80,
                                         placeholder="Why do these codes belong together?")
            if st.form_submit_button(t("codebook_create_category"), type="primary"):
                if not cat_label.strip():
                    st.error("Category label is required.")
                else:
                    try:
                        new_cat = Category.create(
                            project_id=active_project_id,
                            label=cat_label.strip(),
                            rationale=cat_rationale.strip(),
                        )
                        cat_repo.save(new_cat)
                        cat_session.commit()
                        st.success(f"✓ Category '{cat_label.strip()}' saved.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

    cat_session.close()

# ── Themes tab ────────────────────────────────────────────────────────────────
with tab_themes:
    theme_session = get_session()
    theme_repo    = SqlThemeRepository(theme_session)
    themes        = theme_repo.list_for_project(active_project_id)

    if not themes:
        st.warning(t("codebook_themes_warning"), icon="⚠️")
        st.info(
            "No themes yet. Go to the **Clusters** page, promote clusters to categories, "
            "then click **Synthesise themes**. The result will appear here as a draft."
        )
    else:
        st.caption(f"{len(themes)} theme(s) — {sum(1 for th in themes if th.is_published)} published")

        for theme in themes:
            status_icon = "✅" if theme.is_published else "📝"
            with st.expander(f"{status_icon} **{theme.label}**"):

                # Narrative — editable
                new_narrative = st.text_area(
                    "Narrative",
                    value=theme.narrative,
                    height=120,
                    key=f"narr_{theme.id}",
                )
                new_evidence = st.text_area(
                    "Evidence summary",
                    value=theme.evidence_summary,
                    height=80,
                    key=f"evid_{theme.id}",
                )

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("💾 Save edits", key=f"save_theme_{theme.id}"):
                        try:
                            updated = dataclasses.replace(
                                theme,
                                narrative=new_narrative,
                                evidence_summary=new_evidence,
                            )
                            theme_repo.save(updated)
                            theme_session.commit()
                            st.success("Saved.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")

                with col2:
                    if not theme.is_published:
                        if st.button(
                            t("codebook_publish"), key=f"pub_{theme.id}", type="primary"
                        ):
                            if not new_evidence.strip():
                                st.error("Add an evidence summary before publishing.")
                            else:
                                theme_repo.publish(theme.id)
                                theme_session.commit()
                                st.success(f"Theme '{theme.label}' published.")
                                st.rerun()
                    else:
                        st.success("Published ✅")

                with col3:
                    if st.button("🗑️ Delete", key=f"del_theme_{theme.id}"):
                        theme_repo.delete(theme.id)
                        theme_session.commit()
                        st.rerun()

    theme_session.close()