"""
apps/corpus/api.py — Corpus AJAX endpoints
===========================================

POST /api/corpus/import/
  Accepts a transcript .json file (multipart/form-data).
  Returns JSON: { ok: bool, message: str, source_id: str? }
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views import View

from thematic.web.apps.core.services import db_session, get_chroma


class ImportTranscriptView(View):
    def post(self, request):
        project_id = request.session.get("active_project_id")
        corpus_id = request.session.get("active_corpus_id")

        if not project_id or not corpus_id:
            return JsonResponse(
                {"ok": False, "message": _("No active project or corpus.")}, status=400
            )

        uploaded = request.FILES.get("file")
        if not uploaded:
            return JsonResponse({"ok": False, "message": _("No file provided.")}, status=400)

        # Write to a named temp file preserving the .transcript.json suffix
        suffix = ".transcript.json" if uploaded.name.endswith(".transcript.json") else ".json"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            for chunk in uploaded.chunks():
                tmp.write(chunk)
            tmp_path = Path(tmp.name)

        try:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import (
                    SqlSourceRepository,
                    SqlSegmentRepository,
                    SqlCorpusRepository,
                )
                from thematic.infrastructure.importers.transcript_importer import (
                    TranscriptJsonImporter,
                )
                from thematic.application.ingest import IngestTranscriptUseCase

                chroma = get_chroma()
                use_case = IngestTranscriptUseCase(
                    corpus_repo=SqlCorpusRepository(session),
                    source_repo=SqlSourceRepository(session),
                    segment_repo=SqlSegmentRepository(session),
                    importer=TranscriptJsonImporter(),
                    embedding_service=chroma,
                )
                source, count = use_case.execute(
                    path=tmp_path,
                    corpus_id=corpus_id,
                )
            return JsonResponse({
                "ok": True,
                "message": _("Import successful."),
                "source_id": source.id,
                "source_title": source.title,
            })
        except Exception as exc:
            return JsonResponse({"ok": False, "message": str(exc)}, status=500)
        finally:
            tmp_path.unlink(missing_ok=True)
