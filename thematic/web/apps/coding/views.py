"""
apps/coding/views.py
====================

Replaces:  pages/03_coding.py  and  pages/04_codebook.py

The segment list is rendered server-side.  All mutations (apply code,
AI suggest, accept/reject) go through AJAX endpoints in api.py.
"""
from __future__ import annotations

from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView

from thematic.web.apps.core.services import db_session


class CodingView(TemplateView):
    template_name = "coding/coding.html"

    def get(self, request, *args, **kwargs):
        if not request.session.get("active_project_id"):
            return redirect("corpus:index")
        if not request.session.get("active_corpus_id"):
            return redirect("corpus:index")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project_id = self.request.session.get("active_project_id")
        corpus_id = self.request.session.get("active_corpus_id")
        selected_source_id = self.request.GET.get("source")
        speaker_filter = self.request.GET.get("speaker", "INTERVIEWEE")

        with db_session() as session:
            from thematic.infrastructure.db.repositories import (
                SqlSourceRepository,
                SqlSegmentRepository,
                SqlCodeRepository,
            )
            source_repo = SqlSourceRepository(session)
            segment_repo = SqlSegmentRepository(session)
            code_repo = SqlCodeRepository(session)

            sources = source_repo.list_for_corpus(corpus_id)
            codes = code_repo.list_for_project(project_id)

            active_source = None
            segments = []

            if sources:
                # Use selected or default to first
                active_source = next(
                    (s for s in sources if s.id == selected_source_id),
                    sources[0],
                )
                raw_segs = segment_repo.list_for_source(active_source.id)
                segments = (
                    [s for s in raw_segs if s.speaker == "INTERVIEWEE"]
                    if speaker_filter == "INTERVIEWEE"
                    else raw_segs
                )

        ctx.update({
            "sources": sources,
            "active_source": active_source,
            "segments": segments,
            "codes": codes,
            "speaker_filter": speaker_filter,
            "codebook_context": self.request.session.get("codebook_context", ""),
        })
        return ctx

    def post(self, request, *args, **kwargs):
        """Save session-level settings (analyst name, research question)."""
        request.session["analyst"] = request.POST.get("analyst", "analyst").strip()
        request.session["codebook_context"] = request.POST.get("codebook_context", "").strip()
        return redirect(request.path + "?" + request.GET.urlencode())


class CodebookView(TemplateView):
    template_name = "coding/codebook.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project_id = self.request.session.get("active_project_id")

        codes = []
        if project_id:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlCodeRepository
                codes = SqlCodeRepository(session).list_for_project(project_id)

        ctx["codes"] = codes
        return ctx

    def post(self, request, *args, **kwargs):
        """Create a new code."""
        project_id = request.session.get("active_project_id")
        label = request.POST.get("label", "").strip()
        definition = request.POST.get("definition", "").strip()

        if project_id and label:
            with db_session() as session:
                from thematic.application.coding import CreateCodeUseCase
                from thematic.infrastructure.db.repositories import SqlCodeRepository
                CreateCodeUseCase(SqlCodeRepository(session)).execute(
                    project_id=project_id, label=label, definition=definition
                )
        return redirect("coding:codebook")
