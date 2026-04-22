"""
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
    st.session_state["services_ready"] = True


# ─────────────────────────────────────────────
#  Sidebar navigation
# ─────────────────────────────────────────────


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## Thematic Analysis")
        st.caption("Computer-assisted qualitative research")
        st.divider()

        # Show current LLM tier
        if st.session_state.get("llm_tier"):
            st.caption(f"AI: {st.session_state['llm_tier']}")

        st.divider()
        st.caption("Navigation")
        st.page_link("pages/01_corpus.py", label="Corpus", icon="📂")
        st.page_link("pages/02_immersion.py", label="Immersion", icon="📖")
        st.page_link("pages/03_coding.py", label="Coding", icon="🏷️")
        st.page_link("pages/04_codebook.py", label="Codebook", icon="📋")
        st.page_link("pages/05_clusters.py", label="Clusters", icon="🔵")
        st.page_link("pages/06_comparison.py", label="Comparison", icon="⚖️")
        st.page_link("pages/07_export.py", label="Export", icon="📤")
        st.divider()
        st.caption("v0.1.0 — Research preview")


# ─────────────────────────────────────────────
#  Main landing page
# ─────────────────────────────────────────────


def main() -> None:
    _initialise_services()
    _render_sidebar()

    st.title("Thematic Analysis Platform")
    st.caption("Computer-assisted qualitative analysis for interviews and community documents")

    settings = st.session_state.get("settings")
    llm_tier = st.session_state.get("llm_tier", "not configured")
    llm = st.session_state.get("llm")

    # ── Status cards ──────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("AI model", llm_tier if llm else "not ready")

    with col2:
        # Check Ollama availability
        if llm and hasattr(llm, "is_available"):
            available = llm.is_available()
            st.metric("Ollama server", "online" if available else "offline")
        else:
            st.metric("Claude API", "configured" if settings and settings.anthropic_api_key else "no key")

    with col3:
        db_ready = st.session_state.get("db_session_factory") is not None
        st.metric("Database", "ready" if db_ready else "error")

    st.divider()

    # ── Quick start guide ──────────────────────────────────────────────────────
    st.subheader("Quick start")

    with st.expander("1 — Import a transcript from the audio-transcriber", expanded=True):
        st.write(
            "Go to **Corpus → Import** and select a `.transcript.json` file "
            "produced by the audio-transcriber project. The platform preserves "
            "speaker labels, timestamps, and confidence scores."
        )

    with st.expander("2 — Read and familiarise yourself with the material"):
        st.write(
            "Open **Immersion** to read transcripts with audio playback. "
            "Create free-form memos and highlight passages before formal coding begins."
        )

    with st.expander("3 — Code segments and build your codebook"):
        st.write(
            "In **Coding**, select any segment and apply codes manually. "
            "Request AI suggestions at any time — all suggestions start as PENDING "
            "and require your explicit approval."
        )

    with st.expander("4 — Explore clusters and validate themes"):
        st.write(
            "In **Clusters**, review semantic clusters generated from embeddings. "
            "Label clusters, promote them to categories, and synthesise themes "
            "with evidence-backed justification."
        )

    with st.expander("5 — Export your evidence matrix and codebook"):
        st.write(
            "In **Export**, download a versioned codebook, evidence matrix, "
            "and audit trail suitable for academic research workflows."
        )

    st.divider()
    st.info(
        "All AI suggestions are advisory only. The platform never automatically "
        "adopts a model output as a final finding. Every decision is yours.",
        icon="ℹ️",
    )


if __name__ == "__main__":
    main()
