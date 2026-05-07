"""
thematic/presentation/app.py

app.py — Streamlit entry point (Composition Root)
==================================================

Run with:
    streamlit run thematic/presentation/app.py

This file is the only place where concrete infrastructure classes are
instantiated and wired together.  All pages import their dependencies
from ``st.session_state`` — they never construct infrastructure themselves.
"""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st
from thematic.presentation.translations import ts as t
from thematic.presentation.shared_sidebar import render_sidebar

# ─────────────────────────────────────────────
#  Page configuration (must be first Streamlit call)
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="Thematic Analysis Platform",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Dependency wiring (Composition Root)
# ─────────────────────────────────────────────


def _initialise_services() -> None:
    """
    Build the full dependency graph once per session.

    All services are stored in ``st.session_state`` so Streamlit pages
    can access them without re-constructing.  This runs on every page
    load but the ``if "services_ready"`` guard makes it a no-op after
    the first call.
    """
    if st.session_state.get("services_ready"):
        return

    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")

        db_url: str = "sqlite:///./thematic.db"
        chroma_path: str = "./chroma_store"
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
        embedding_device: str | None = None
        ollama_model: str = "mistral:7b"
        ollama_host: str = "http://localhost:11434"
        anthropic_api_key: str = ""
        default_analyst: str = "analyst"
        use_claude: bool = False

    settings = Settings()
    st.session_state["settings"] = settings

    # ── Database ──────────────────────────────────────────────────────────────
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Import ORM models to ensure tables are created.
    # (In production, use Alembic migrations instead.)
    try:
        from thematic.infrastructure.db import models as _db_models  # noqa: F401
        engine = create_engine(settings.db_url, echo=False)
        _db_models.Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine)
        st.session_state["db_session_factory"] = SessionLocal
    except Exception as e:
        st.warning(f"Database initialisation warning: {e}")
        st.session_state["db_session_factory"] = None

    # ── LLM adapter ───────────────────────────────────────────────────────────
    if settings.use_claude and settings.anthropic_api_key:
        from thematic.infrastructure.llm.anthropic_adapter import AnthropicLLMAdapter
        llm = AnthropicLLMAdapter(api_key=settings.anthropic_api_key)
        st.session_state["llm_tier"] = "Claude API (Tier 2)"
    else:
        from thematic.infrastructure.llm.ollama_adapter import OllamaLLMAdapter
        llm = OllamaLLMAdapter(model=settings.ollama_model, host=settings.ollama_host)
        st.session_state["llm_tier"] = f"Ollama {settings.ollama_model} (Tier 1)"

    st.session_state["llm"] = llm

    # ── Embedding service (ChromaDB) ──────────────────────────────────────────
    from thematic.infrastructure.embeddings.chroma_service import ChromaEmbeddingService

    chroma = ChromaEmbeddingService(
        persist_path=settings.chroma_path,
        model_name=settings.embedding_model,
        device=settings.embedding_device,
        project_id=st.session_state.get("active_project_id", ""),
    )
    st.session_state["chroma_service"] = chroma

    st.session_state["services_ready"] = True


# ─────────────────────────────────────────────
#  Sidebar navigation is now imported from shared_sidebar
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
#  Main landing page
# ─────────────────────────────────────────────


def main() -> None:
    _initialise_services()
    render_sidebar()

    st.title(t('main_title'))
    st.caption(t('main_subtitle'))

    settings = st.session_state.get("settings")
    llm_tier = st.session_state.get("llm_tier", "not configured")
    llm = st.session_state.get("llm")

    # ── Status cards ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(t('status_ai_model'), llm_tier if llm else "not ready")

    with col2:
        # Check Ollama availability
        if llm and hasattr(llm, "is_available"):
            available = llm.is_available()
            st.metric(t('status_ollama'), t('status_online') if available else t('status_offline'))
        else:
            st.metric("Claude API", "configured" if settings and settings.anthropic_api_key else "no key")

    with col3:
        db_ready = st.session_state.get("db_session_factory") is not None
        st.metric(t('status_database'), t('status_ready') if db_ready else t('status_error'))

    st.divider()

    # ── Quick start guide ──────────────────────────────────────────────────────
    st.subheader(t('quick_start_title'))

    with st.expander(t('qs_step_1_title'), expanded=True):
        st.write(t('qs_step_1_body'))

    with st.expander(t('qs_step_2_title')):
        st.write(t('qs_step_2_body'))

    with st.expander(t('qs_step_3_title')):
        st.write(t('qs_step_3_body'))

    with st.expander(t('qs_step_4_title')):
        st.write(t('qs_step_4_body'))

    with st.expander(t('qs_step_5_title')):
        st.write(t('qs_step_5_body'))

    st.divider()
    st.info(
        t('advisory_note'),
        icon="ℹ️",
    )


if __name__ == "__main__":
    main()
