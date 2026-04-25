"""
apps/export/views.py
====================

Replaces:  pages/07_export.py  (all demo data removed, real use cases wired)
"""
from __future__ import annotations

from datetime import datetime, timezone

from django.http import HttpResponse
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django.views import View

from thematic.web.apps.core.services import db_session


class ExportView(TemplateView):
    template_name = "export/export.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project_id = self.request.session.get("active_project_id")
        codes, sources = [], []
        if project_id:
            corpus_id = self.request.session.get("active_corpus_id")
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlCodeRepository,
                    SqlSourceRepository,
                )
                codes = SqlCodeRepository(session).list_for_project(project_id)
                if corpus_id:
                    sources = SqlSourceRepository(session).list_for_corpus(corpus_id)
        ctx.update({"codes": codes, "sources": sources, "code_count": len(codes)})
        return ctx


class DownloadMatrixView(View):
    """Generate and download the evidence matrix as CSV."""

    def get(self, request):
        project_id = request.session.get("active_project_id")
        speaker_filter_raw = request.GET.get("speaker", "INTERVIEWEE")
        speaker_filter = None if speaker_filter_raw == "ALL" else [speaker_filter_raw]
        include_ai = request.GET.get("include_ai", "1") == "1"

        if not project_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("No active project.")

        with db_session() as session:
            from thematic.application.export import (
                BuildEvidenceMatrixUseCase,
                ExportEvidenceMatrixCsvUseCase,
            )
            from thematic.infrastructure.db.repositories import (
                SqlCodingDecisionRepository,
                SqlSegmentRepository,
                SqlCodeRepository,
                SqlSourceRepository,
            )
            matrix = BuildEvidenceMatrixUseCase(
                decision_repo=SqlCodingDecisionRepository(session),
                segment_repo=SqlSegmentRepository(session),
                code_repo=SqlCodeRepository(session),
                source_repo=SqlSourceRepository(session),
            ).execute(
                project_id,
                speaker_filter=speaker_filter,
                include_ai=include_ai,
            )
            csv_str = ExportEvidenceMatrixCsvUseCase().execute(matrix)

        response = HttpResponse(csv_str, content_type="text/csv; charset=utf-8")
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
        response["Content-Disposition"] = f'attachment; filename="evidence_matrix_{ts}.csv"'
        return response


class DownloadCodebookView(View):
    """Download the codebook as versioned JSON via ExportCodebookJsonUseCase."""

    def get(self, request):
        project_id = request.session.get("active_project_id")
        if not project_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("No active project.")

        with db_session() as session:
            from thematic.application.export import ExportCodebookJsonUseCase
            from thematic.infrastructure.db.repositories import SqlCodeRepository
            payload = ExportCodebookJsonUseCase(
                SqlCodeRepository(session)
            ).execute(project_id)

        response = HttpResponse(payload, content_type="application/json; charset=utf-8")
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
        response["Content-Disposition"] = f'attachment; filename="codebook_{ts}.json"'
        return response


class DownloadAuditView(View):
    """Download the full audit trail via ExportAuditTrailUseCase."""

    def get(self, request):
        project_id = request.session.get("active_project_id")
        if not project_id:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("No active project.")

        with db_session() as session:
            from thematic.application.export import ExportAuditTrailUseCase
            from thematic.infrastructure.db.repositories import (
                SqlCodingDecisionRepository,
                SqlModelRunRepository,
            )
            payload = ExportAuditTrailUseCase(
                decision_repo=SqlCodingDecisionRepository(session),
                run_repo=SqlModelRunRepository(session),
            ).execute(project_id)

        response = HttpResponse(payload, content_type="application/json; charset=utf-8")
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M")
        response["Content-Disposition"] = f'attachment; filename="audit_trail_{ts}.json"'
        return response
