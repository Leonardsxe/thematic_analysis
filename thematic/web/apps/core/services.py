"""
apps/core/services.py — Composition Root
==========================================

This module is the Django equivalent of Streamlit's _initialise_services().
It is called ONCE inside CoreConfig.ready() at server startup.

All infrastructure objects are stored as module-level singletons accessible
via get_*() helpers.  Views import helpers, not constructors — they never
instantiate infrastructure themselves.

Dependency graph
----------------
  InfraSettings (pydantic)
      ↓
  SQLAlchemy engine + SessionLocal factory
      ↓
  Repository factories (one per entity type)

  LLMAdapter (Ollama | Anthropic)  ← independent of DB

  ChromaEmbeddingService           ← independent of DB
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

# ── Module-level singletons set by _bootstrap() ───────────────────────────────
_session_factory = None
_llm = None
_llm_tier: str = "not configured"
_chroma = None
_ready = False


def _bootstrap() -> None:
    """
    Initialise all infrastructure singletons.  Called exactly once by
    CoreConfig.ready().  Idempotent — safe if called again.
    """
    global _session_factory, _llm, _llm_tier, _chroma, _ready

    if _ready:
        return

    infra = django_settings.INFRA_SETTINGS

    # ── SQLAlchemy ─────────────────────────────────────────────────────────────
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from thematic.infrastructure.db import models as _db_models  # noqa: F401

        engine = create_engine(infra.db_url, echo=False)
        _db_models.Base.metadata.create_all(engine)
        _session_factory = sessionmaker(bind=engine)
        logger.info("Database ready: %s", infra.db_url)
    except Exception:
        logger.exception("Database initialisation failed")
        _session_factory = None

    # ── LLM adapter ────────────────────────────────────────────────────────────
    try:
        if infra.use_claude and infra.anthropic_api_key:
            from thematic.infrastructure.llm.anthropic_adapter import AnthropicLLMAdapter
            _llm = AnthropicLLMAdapter(api_key=infra.anthropic_api_key)
            _llm_tier = "Claude API (Tier 2)"
        else:
            from thematic.infrastructure.llm.ollama_adapter import OllamaLLMAdapter
            _llm = OllamaLLMAdapter(model=infra.ollama_model, host=infra.ollama_host)
            _llm_tier = f"Ollama {infra.ollama_model} (Tier 1)"
        logger.info("LLM ready: %s", _llm_tier)
    except Exception:
        logger.exception("LLM adapter initialisation failed")
        _llm = None

    # ── Chroma embedding service ───────────────────────────────────────────────
    try:
        from thematic.infrastructure.embeddings.chroma_service import ChromaEmbeddingService
        _chroma = ChromaEmbeddingService(
            persist_path=infra.chroma_path,
            model_name=infra.embedding_model,
            device=infra.embedding_device,
        )
        logger.info("ChromaDB ready: %s", infra.chroma_path)
    except Exception:
        logger.exception("ChromaDB initialisation failed")
        _chroma = None

    _ready = True


# ── Public accessors ──────────────────────────────────────────────────────────

def get_llm():
    """Return the configured LLM adapter (Ollama or Anthropic)."""
    return _llm


def get_llm_tier() -> str:
    return _llm_tier


def get_chroma():
    """Return the ChromaEmbeddingService singleton."""
    return _chroma


@contextmanager
def db_session() -> Generator:
    """
    Context manager that yields a fresh SQLAlchemy session and closes it
    after use.  Use in every view that touches the database:

        with db_session() as session:
            repo = SqlProjectRepository(session)
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Check settings and server logs.")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_db_ready() -> bool:
    return _session_factory is not None


def is_llm_ready() -> bool:
    return _llm is not None
