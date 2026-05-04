"""
apps/coding/api.py — Coding AJAX endpoints
===========================================

All views return JSON.  The vanilla JS in coding.js calls these with fetch().

  POST /api/coding/apply/      → ApplyCodeUseCase
  POST /api/coding/suggest/    → SuggestCodesUseCase
  POST /api/coding/accept/     → AcceptSuggestionUseCase (+ auto-create code)
  POST /api/coding/reject/     → marks suggestion rejected
  GET  /api/segments/similar/  → FindSimilarSegmentsUseCase + ChromaDB
"""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views import View

from thematic.web.apps.core.services import db_session, get_llm, get_chroma


def _json_body(request) -> dict:
    try:
        return json.loads(request.body)
    except Exception:
        return {}


class ApplyCodeView(View):
    def post(self, request):
        data = _json_body(request)
        segment_id = data.get("segment_id")
        code_id = data.get("code_id")
        analyst = request.session.get("analyst", "analyst")

        if not segment_id or not code_id:
            return JsonResponse({"ok": False, "message": _("Missing segment_id or code_id.")}, status=400)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlCodingDecisionRepository,
                    SqlCodeRepository,
                    SqlSegmentRepository,
                )
                from thematic.application.coding import ApplyCodeUseCase
                ApplyCodeUseCase(
                    SqlCodingDecisionRepository(session),
                    SqlCodeRepository(session),
                    SqlSegmentRepository(session),
                ).execute(segment_id=segment_id, code_id=code_id, analyst=analyst)
            return JsonResponse({"ok": True})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class SuggestCodesView(View):
    def post(self, request):
        data = _json_body(request)
        segment_id = data.get("segment_id")
        project_id = request.session.get("active_project_id")
        codebook_context = request.session.get("codebook_context", "")

        llm = get_llm()
        if llm is None:
            return JsonResponse({"ok": False, "message": _("No LLM configured.")}, status=503)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlCodeRepository,
                    SqlSegmentRepository,
                    SqlAISuggestionRepository,
                    SqlModelRunRepository,
                )
                from thematic.application.coding import SuggestCodesUseCase
                suggestions = SuggestCodesUseCase(
                    llm_service=llm,
                    code_repo=SqlCodeRepository(session),
                    segment_repo=SqlSegmentRepository(session),
                    suggestion_repo=SqlAISuggestionRepository(session),
                    run_repo=SqlModelRunRepository(session),
                ).execute(
                    segment_id=segment_id,
                    project_id=project_id,
                    codebook_context=codebook_context,
                )
            return JsonResponse({
                "ok": True,
                "suggestions": [
                    {
                        "id": str(s.id),
                        "label": s.suggested_code_label,
                        "confidence": s.confidence,
                        "justification": s.justification,
                    }
                    for s in suggestions
                ],
            })
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class AcceptSuggestionView(View):
    """
    Accept an AI suggestion: find-or-create the code, apply it to the segment.
    Fixes the NotImplementedError in AcceptSuggestionUseCase by implementing
    the logic here until the use case is completed in the domain layer.
    """
    def post(self, request):
        data = _json_body(request)
        segment_id = data.get("segment_id")
        label = data.get("label")
        justification = data.get("justification", "")
        project_id = request.session.get("active_project_id")
        analyst = request.session.get("analyst", "analyst")

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlCodeRepository,
                    SqlCodingDecisionRepository,
                    SqlSegmentRepository,
                )
                from thematic.application.coding import ApplyCodeUseCase, CreateCodeUseCase

                code_repo = SqlCodeRepository(session)
                code = code_repo.get_by_label(project_id, label)

                if not code:
                    code = CreateCodeUseCase(code_repo).execute(
                        project_id=project_id,
                        label=label,
                        definition=f"AI suggested: {justification}",
                    )

                ApplyCodeUseCase(
                    SqlCodingDecisionRepository(session),
                    SqlCodeRepository(session),
                    SqlSegmentRepository(session),
                ).execute(segment_id=segment_id, code_id=code.id, analyst=analyst)

            return JsonResponse({"ok": True, "code_id": str(code.id)})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class RejectSuggestionView(View):
    def post(self, request):
        # Suggestions live in session until page reload — nothing to persist yet.
        return JsonResponse({"ok": True})


class ExcerptsView(View):
    """
    GET /api/coding/excerpts/?code_id=…&source_id=…
    Returns all excerpts for a (code, source) cell in the comparison matrix.
    """
    def get(self, request):
        code_id = request.GET.get("code_id")
        source_id = request.GET.get("source_id")
        if not code_id or not source_id:
            return JsonResponse({"ok": False, "message": "Missing params."}, status=400)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlCodingDecisionRepository,
                    SqlSegmentRepository,
                )
                decisions = SqlCodingDecisionRepository(session).list_for_code(code_id)
                seg_repo = SqlSegmentRepository(session)
                excerpts = []
                for dec in decisions:
                    seg = seg_repo.get(dec.segment_id)
                    if seg and seg.source_id == source_id:
                        excerpts.append({
                            "text": seg.text,
                            "speaker": seg.speaker or "UNKNOWN",
                            "start_s": seg.start_s,
                            "is_ai": dec.is_ai,
                            "analyst": dec.analyst,
                        })
            return JsonResponse({"ok": True, "excerpts": excerpts})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class FindSimilarView(View):
    def get(self, request):
        query = request.GET.get("q", "").strip()
        project_id = request.session.get("active_project_id")

        if not query:
            return JsonResponse({"ok": False, "message": _("No query.")}, status=400)

        chroma = get_chroma()
        if chroma is None:
            return JsonResponse({"ok": False, "message": _("Embedding service not ready.")}, status=503)

        try:
            results = chroma.find_similar(query, top_k=5, project_id=project_id)
            segments = []
            if results:
                with db_session() as session:
                    from thematic.infrastructure.db.repositories import SqlSegmentRepository
                    repo = SqlSegmentRepository(session)
                    for seg_id, score in results:
                        seg = repo.get(seg_id)
                        if seg:
                            segments.append({
                                "id": str(seg.id),
                                "speaker": seg.speaker,
                                "text": seg.text[:300],
                                "score": round(score, 3),
                            })
            return JsonResponse({"ok": True, "segments": segments})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class CreateCategoryView(View):
    def post(self, request):
        data = _json_body(request)
        project_id = request.session.get("active_project_id")
        label = data.get("label", "").strip()
        rationale = data.get("rationale", "").strip()

        if not project_id or not label:
            return JsonResponse({"ok": False, "message": "Missing project_id or label."}, status=400)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlCategoryRepository
                from thematic.domain.entities import Category
                cat = Category.create(project_id=project_id, label=label, rationale=rationale)
                SqlCategoryRepository(session).save(cat)
            return JsonResponse({"ok": True, "category_id": cat.id})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class AssignCodeToCategoryView(View):
    def post(self, request):
        data = _json_body(request)
        code_id = data.get("code_id")
        category_id = data.get("category_id")

        if not code_id:
            return JsonResponse({"ok": False, "message": "Missing code_id."}, status=400)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlCodeRepository
                repo = SqlCodeRepository(session)
                code = repo.get(code_id)
                if not code:
                    return JsonResponse({"ok": False, "message": "Code not found."}, status=404)
                
                from dataclasses import replace
                updated_code = replace(code, category_id=category_id if category_id else None)
                repo.save(updated_code)
            return JsonResponse({"ok": True})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class SaveThemeView(View):
    def post(self, request):
        data = _json_body(request)
        project_id = request.session.get("active_project_id")
        theme_id = data.get("theme_id")
        label = data.get("label", "").strip()
        narrative = data.get("narrative", "").strip()
        evidence_summary = data.get("evidence_summary", "").strip()

        if not project_id or not label:
            return JsonResponse({"ok": False, "message": "Missing project_id or label."}, status=400)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlThemeRepository
                from thematic.domain.entities import Theme
                from dataclasses import replace
                repo = SqlThemeRepository(session)
                if theme_id:
                    theme = repo.get(theme_id)
                    if theme:
                        theme = replace(theme, label=label, narrative=narrative, evidence_summary=evidence_summary)
                    else:
                        return JsonResponse({"ok": False, "message": "Theme not found."}, status=404)
                else:
                    theme = Theme.create(project_id=project_id, label=label)
                    theme = replace(theme, narrative=narrative, evidence_summary=evidence_summary)
                
                repo.save(theme)
            return JsonResponse({"ok": True, "theme_id": theme.id})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)


class PublishThemeView(View):
    def post(self, request, theme_id):
        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlThemeRepository
                from dataclasses import replace
                repo = SqlThemeRepository(session)
                theme = repo.get(theme_id)
                if not theme:
                    return JsonResponse({"ok": False, "message": "Theme not found."}, status=404)
                
                theme = replace(theme, is_published=True)
                repo.save(theme)
            return JsonResponse({"ok": True})
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)
