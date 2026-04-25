"""apps/core/context_processors.py

Injects active_project, system status, and i18n helpers into every template.
"""
from __future__ import annotations

from thematic.web.apps.core import services


def active_project(request) -> dict:
    """
    Make the active project and system status available in every template
    without having to pass them explicitly from each view.
    """
    ctx: dict = {
        "llm_tier": services.get_llm_tier(),
        "db_ready": services.is_db_ready(),
        "llm_ready": services.is_llm_ready(),
        "active_project_id": request.session.get("active_project_id"),
        "active_project_name": request.session.get("active_project_name"),
        "active_corpus_id": request.session.get("active_corpus_id"),
        "active_corpus_name": request.session.get("active_corpus_name"),
        "analyst": request.session.get("analyst", "analyst"),
    }
    return ctx
