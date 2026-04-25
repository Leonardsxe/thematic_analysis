"""
apps/corpus/views.py
====================

Replaces:  thematic/presentation/pages/01_corpus.py

Three tabs → three views:
  GET  /corpus/          → CorpusView   (project selector + corpus list)
  GET  /corpus/import/   → ImportView   (file-upload form)
  GET  /corpus/sources/  → SourceListView (segments preview)
"""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import TemplateView

from thematic.web.apps.core.services import db_session


class CorpusView(TemplateView):
    template_name = "corpus/corpus.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        with db_session() as session:
            from thematic.infrastructure.db.repositories import (
                SqlProjectRepository,
                SqlCorpusRepository,
            )
            projects = SqlProjectRepository(session).list_all()
            active_id = self.request.session.get("active_project_id")
            corpora = (
                SqlCorpusRepository(session).list_for_project(active_id)
                if active_id else []
            )
        ctx["projects"] = projects
        ctx["corpora"] = corpora
        return ctx

    def post(self, request: HttpRequest) -> HttpResponse:
        """Create a new project or activate an existing one."""
        action = request.POST.get("action")

        with db_session() as session:
            from thematic.infrastructure.db.repositories import SqlProjectRepository
            from thematic.domain.entities import Project

            repo = SqlProjectRepository(session)

            if action == "create":
                name = request.POST.get("name", "").strip()
                rq = request.POST.get("research_question", "").strip()
                if not name:
                    messages.error(request, _("Project name is required."))
                    return redirect("corpus:index")
                project = Project(name=name, research_question=rq)
                repo.save(project)
                request.session["active_project_id"] = project.id
                request.session["active_project_name"] = project.name
                messages.success(request, _("Project created."))

            elif action == "activate":
                project_id = request.POST.get("project_id")
                project = repo.get(project_id)
                if project:
                    request.session["active_project_id"] = project.id
                    request.session["active_project_name"] = project.name
                    request.session.pop("active_corpus_id", None)
                    request.session.pop("active_corpus_name", None)
                    messages.success(request, _("Project activated."))

            elif action == "activate_corpus":
                from thematic.infrastructure.db.repositories import SqlCorpusRepository
                corpus_id = request.POST.get("corpus_id")
                corpus = SqlCorpusRepository(session).get(corpus_id)
                if corpus:
                    request.session["active_corpus_id"] = corpus.id
                    request.session["active_corpus_name"] = corpus.name
                    messages.success(request, _("Corpus activated."))

            elif action == "create_corpus":
                from thematic.infrastructure.db.repositories import SqlCorpusRepository
                from thematic.domain.entities import Corpus
                project_id = request.session.get("active_project_id")
                if not project_id:
                    messages.error(request, _("Select a project first."))
                    return redirect("corpus:index")
                name = request.POST.get("corpus_name", "").strip()
                corpus = Corpus(project_id=project_id, name=name)
                SqlCorpusRepository(session).save(corpus)
                request.session["active_corpus_id"] = corpus.id
                request.session["active_corpus_name"] = corpus.name
                messages.success(request, _("Corpus created."))

        return redirect("corpus:index")


class ImportView(TemplateView):
    template_name = "corpus/import.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_project"] = bool(self.request.session.get("active_project_id"))
        ctx["has_corpus"] = bool(self.request.session.get("active_corpus_id"))
        return ctx


class SourceListView(TemplateView):
    template_name = "corpus/sources.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        corpus_id = self.request.session.get("active_corpus_id")
        sources = []
        total_segments = 0
        total_words = 0

        if corpus_id:
            with db_session() as session:
                from collections import Counter
                from thematic.infrastructure.db.repositories import (
                    SqlSourceRepository,
                    SqlSegmentRepository,
                )
                seg_repo = SqlSegmentRepository(session)
                raw = SqlSourceRepository(session).list_for_corpus(corpus_id)

                for src in raw:
                    segs = seg_repo.list_for_source(src.id)
                    speaker_counts = dict(Counter(
                        s.speaker for s in segs if s.speaker
                    ))
                    word_count = sum(s.word_count for s in segs)
                    total_segments += len(segs)
                    total_words += word_count
                    sources.append({
                        "source": src,
                        "segments": segs,
                        "segment_count": len(segs),
                        "word_count": word_count,
                        "speaker_counts": speaker_counts,
                    })

        ctx["sources"] = sources
        ctx["total_segments"] = total_segments
        ctx["total_words"] = total_words
        return ctx
