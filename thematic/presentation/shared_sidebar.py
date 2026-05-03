"""
thematic/presentation/shared_sidebar.py
Call render_sidebar() at the TOP of every page file.
"""
from __future__ import annotations
import streamlit as st
from thematic.presentation.translations import ts as t


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"## {t('nav_title')}")
        st.caption(t("nav_subtitle"))

        st.divider()
        current_lang = st.session_state.get("language", "en")
        c1, c2 = st.columns(2)
        if c1.button("🇺🇸 EN", use_container_width=True,
                     type="primary" if current_lang == "en" else "secondary"):
            if current_lang != "en":
                st.session_state["language"] = "en"
                st.rerun()
        if c2.button("🇨🇴 ES", use_container_width=True,
                     type="primary" if current_lang == "es" else "secondary"):
            if current_lang != "es":
                st.session_state["language"] = "es"
                st.rerun()

        st.divider()
        project_name = st.session_state.get("active_project_name")
        corpus_name  = st.session_state.get("active_corpus_name")
        if project_name:
            st.caption(t("active_project"))
            st.markdown(f"**{project_name}**")
            if corpus_name:
                st.caption(corpus_name)
        else:
            st.warning(t("no_project_selected"), icon="⚠️")

        st.divider()
        st.caption(t("nav_header"))
        st.page_link("app.py",                label=t("nav_dashboard"),  icon="🏠")
        st.page_link("pages/01_corpus.py",    label=t("nav_corpus"),     icon="📂")
        st.page_link("pages/02_immersion.py", label=t("nav_immersion"),  icon="📖")
        st.page_link("pages/03_coding.py",    label=t("nav_coding"),     icon="🏷️")
        st.page_link("pages/04_codebook.py",  label=t("nav_codebook"),   icon="📋")
        st.page_link("pages/05_clusters.py",  label=t("nav_clusters"),   icon="🔵")
        st.page_link("pages/06_comparison.py",label=t("nav_comparison"), icon="⚖️")
        st.page_link("pages/07_export.py",    label=t("nav_export"),     icon="📤")

        st.divider()
        db_ok    = st.session_state.get("db_session_factory") is not None
        llm_tier = st.session_state.get("llm_tier", "")
        st.caption(f"{'✅' if db_ok else '❌'} DB  ·  {llm_tier or '⚠️ No LLM'}")
        st.caption(t("version_tag"))