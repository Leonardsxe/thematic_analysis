"""
04_codebook.py — Codebook management
=====================================

Create, edit, deprecate, and organise codes into categories and themes.
The codebook is versioned — every edit increments the version counter.
"""

from __future__ import annotations

import streamlit as st
from thematic.presentation.translations import t
from thematic.infrastructure.db.repositories import SqlCodeRepository
from thematic.application.coding import CreateCodeUseCase

# ── Infrastructure ────────────────────────────────────────────────────────────
def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised. Please check app.py.")
        st.stop()
    return factory()

st.set_page_config(page_title=f"{t('nav_codebook')} | {t('nav_title')}", layout="wide")

st.title("Codebook")

tab_codes, tab_categories, tab_themes = st.tabs(["Codes", "Categories", "Themes"])

active_project_id = st.session_state.get("active_project_id")

if not active_project_id:
    st.warning("Please select a project first in the 'Corpus' page.")
    st.stop()

session = get_session()
code_repo = SqlCodeRepository(session)
all_codes = code_repo.list_for_project(active_project_id)

# ── Codes tab ─────────────────────────────────────────────────────────────────
with tab_codes:
    col_list, col_new = st.columns([2, 1])

    with col_list:
        st.subheader(f"Codes ({len(all_codes)})")

        search = st.text_input("Filter codes", placeholder="Search…", label_visibility="collapsed")
        filtered = [c for c in all_codes if not search or search.lower() in c.label.lower()]

        if not filtered:
            st.info("No codes found. Create one on the right →")
        else:
            for code in filtered:
                with st.expander(f"**{code.label}** · v{code.version}"):
                    st.markdown(f"**Definition:** {code.definition}")
                    st.markdown(f"**Inclusion:** {code.inclusion_criteria}")
                    st.markdown(f"**Exclusion:** {code.exclusion_criteria}")

                    if st.button("Deprecate", key=f"dep_{code.id}"):
                        st.info("Deprecation not implemented in DB yet.")

    with col_new:
        st.subheader("New code")
        with st.form("new_code_form"):
            label = st.text_input("Label", placeholder="exclusion_from_spaces")
            definition = st.text_area("Definition", height=80,
                                       placeholder="What this code captures…")
            inclusion = st.text_area("Inclusion criteria", height=60,
                                      placeholder="Must be present to apply this code…")
            exclusion = st.text_area("Exclusion criteria", height=60,
                                      placeholder="What disqualifies this code…")
            examples = st.text_area("Examples (one per line)", height=60)
            submitted = st.form_submit_button("Create code")
            if submitted:
                if not label.strip():
                    st.error("Label is required.")
                elif not definition.strip():
                    st.error("Definition is required.")
                else:
                    try:
                        create_use_case = CreateCodeUseCase(code_repo)
                        create_use_case.execute(
                            project_id=active_project_id,
                            label=label,
                            definition=definition,
                            inclusion_criteria=inclusion,
                            exclusion_criteria=exclusion,
                        )
                        session.commit()
                        st.success(f"Code '{label}' created.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to create code: {e}")
    
    session.close()

# ── Categories tab ────────────────────────────────────────────────────────────
with tab_categories:
    st.subheader("Categories")
    st.info(
        "Categories group related codes. Promote clusters from the "
        "**Clusters** page to create categories automatically, or create them manually here."
    )

    demo_categories = [
        {"label": "Spatial exclusion and displacement", "codes": ["exclusion_from_spaces"], "theme": None},
        {"label": "Community resilience and self-organisation", "codes": ["community_self_organization"], "theme": None},
    ]

    for cat in demo_categories:
        with st.container(border=True):
            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.markdown(f"**{cat['label']}**")
                st.caption("Codes: " + ", ".join(f"`{c}`" for c in cat["codes"]))
            with col_b:
                if st.button("Promote to theme", key=f"promote_{cat['label']}"):
                    st.success(f"Promoted '{cat['label']}' to theme.")

    with st.form("new_category"):
        cat_label = st.text_input("New category label")
        cat_rationale = st.text_area("Rationale", height=60)
        if st.form_submit_button("Create category"):
            if cat_label.strip():
                st.success(f"Category '{cat_label}' created.")

# ── Themes tab ────────────────────────────────────────────────────────────────
with tab_themes:
    st.subheader("Themes")
    st.warning(
        "A theme requires evidence-backed justification before it can be published. "
        "Use the **Clusters** page and the AI synthesis tools to build your evidence base.",
        icon="⚠️",
    )

    demo_themes = [
        {
            "label": "Contested belonging in community pedagogy",
            "narrative": "Community educators experience a fundamental tension between institutional recognition and autonomous practice.",
            "evidence_summary": "Multiple participants describe conditional support that requires adopting external methodologies.",
            "is_published": False,
        }
    ]

    for theme in demo_themes:
        with st.container(border=True):
            published_badge = " ✓ Published" if theme["is_published"] else " · Draft"
            st.markdown(f"**{theme['label']}**{published_badge}")
            st.markdown(theme["narrative"])
            st.caption(f"Evidence: {theme['evidence_summary']}")

            col_p, col_e = st.columns(2)
            with col_p:
                if not theme["is_published"]:
                    if st.button("Publish", key=f"pub_{theme['label']}"):
                        st.success("Theme published.")
            with col_e:
                if st.button("Edit narrative", key=f"edit_theme_{theme['label']}"):
                    st.session_state[f"editing_theme_{theme['label']}"] = True
