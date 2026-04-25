"""
apps/analysis/views.py
=======================

Replaces:  pages/02_immersion.py, 05_clusters.py, 06_comparison.py
"""
from __future__ import annotations

from django.shortcuts import redirect
from django.views.generic import TemplateView

from thematic.web.apps.core.services import db_session, get_chroma


class ImmersionView(TemplateView):
    template_name = "analysis/immersion.html"

    def get(self, request, *args, **kwargs):
        if not request.session.get("active_corpus_id"):
            return redirect("corpus:index")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        corpus_id = self.request.session.get("active_corpus_id")
        selected_source_id = self.request.GET.get("source")
        speaker_filter = self.request.GET.getlist("speaker") or ["INTERVIEWEE"]

        with db_session() as session:
            from thematic.infrastructure.db.repositories import (
                SqlSourceRepository,
                SqlSegmentRepository,
            )
            sources = SqlSourceRepository(session).list_for_corpus(corpus_id)
            active_source = None
            segments = []

            if sources:
                active_source = next(
                    (s for s in sources if s.id == selected_source_id),
                    sources[0],
                )
                raw = SqlSegmentRepository(session).list_for_source(active_source.id)
                segments = (
                    [s for s in raw if s.speaker in speaker_filter]
                    if speaker_filter != ["ALL"]
                    else raw
                )

        ctx.update({
            "sources": sources,
            "active_source": active_source,
            "segments": segments,
            "speaker_filter": speaker_filter,
        })
        return ctx


class ClustersView(TemplateView):
    """
    Cluster explorer.  Clustering is triggered via a POST; results are stored
    in the session and displayed on reload.  Real DB integration replaces
    demo_clusters from the Streamlit version.
    """
    template_name = "analysis/clusters.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project_id = self.request.session.get("active_project_id")
        clusters = []
        if project_id:
            with db_session() as session:
                from thematic.infrastructure.db.repositories import SqlClusterRepository
                clusters = SqlClusterRepository(session).list_for_project(project_id)
        ctx["clusters"] = clusters
        ctx["show_reviewed"] = self.request.GET.get("show_reviewed") == "1"
        return ctx

    def post(self, request, *args, **kwargs):
        """Trigger clustering run."""
        from django.contrib import messages
        from django.utils.translation import gettext as _

        project_id = request.session.get("active_project_id")
        if not project_id:
            messages.error(request, _("No active project."))
            return redirect("analysis:clusters")

        min_size = int(request.POST.get("min_cluster_size", 5))
        request_labels = request.POST.get("request_labels") == "on"

        chroma = get_chroma()
        if chroma is None:
            messages.error(request, _("Embedding service not ready. Cannot cluster."))
            return redirect("analysis:clusters")

        try:
            from thematic.application.clustering import RunClusteringUseCase, ClusteringConfig
            from thematic.infrastructure.db.repositories import (
                SqlSegmentRepository,
                SqlClusterRepository,
                SqlModelRunRepository,
            )
            from thematic.web.apps.core.services import get_llm

            with db_session() as session:
                llm = get_llm() if request_labels else None
                use_case = RunClusteringUseCase(
                    embedding_service=chroma,
                    segment_repo=SqlSegmentRepository(session),
                    cluster_repo=SqlClusterRepository(session),
                    run_repo=SqlModelRunRepository(session),
                    llm_service=llm,
                    config=ClusteringConfig(min_cluster_size=min_size),
                )
                clusters = use_case.execute(project_id=project_id)

            if clusters:
                messages.success(
                    request,
                    _("Clustering complete: %(n)d cluster(s) found.") % {"n": len(clusters)}
                )
            else:
                messages.warning(
                    request,
                    _("No clusters found. Segments may not be embedded yet, or the corpus is too small.")
                )
        except Exception as exc:
            messages.error(request, str(exc))

        return redirect("analysis:clusters")


class ComparisonView(TemplateView):
    """
    Cross-source evidence matrix — fully wired to DB.
    Builds a pivot: rows = codes, columns = sources, cells = decision count.
    """
    template_name = "analysis/comparison.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project_id = self.request.session.get("active_project_id")
        corpus_id = self.request.session.get("active_corpus_id")
        speaker_filter = self.request.GET.get("speaker", "INTERVIEWEE")
        hide_empty = self.request.GET.get("hide_empty", "1") == "1"

        if not project_id or not corpus_id:
            ctx.update({"codes": [], "sources": [], "matrix_rows": [],
                        "total_decisions": 0, "ai_decisions": 0,
                        "speaker_filter": speaker_filter, "hide_empty": hide_empty})
            return ctx

        with db_session() as session:
            from collections import defaultdict
            from thematic.infrastructure.db.repositories import (
                SqlCodeRepository,
                SqlSourceRepository,
                SqlSegmentRepository,
                SqlCodingDecisionRepository,
            )

            codes   = SqlCodeRepository(session).list_for_project(project_id)
            sources = SqlSourceRepository(session).list_for_corpus(corpus_id)
            all_decisions = SqlCodingDecisionRepository(session).list_for_project(project_id)

            # Build segment→source index and apply speaker filter
            seg_repo = SqlSegmentRepository(session)
            seg_to_source: dict[str, str] = {}
            seg_speaker: dict[str, str] = {}

            source_ids = {s.id for s in sources}
            for src in sources:
                for seg in seg_repo.list_for_source(src.id):
                    seg_to_source[seg.id] = src.id
                    seg_speaker[seg.id] = seg.speaker or "UNKNOWN"

            # Count decisions per (code_id, source_id)
            # Structure: pivot[code_id][source_id] = {"count": int, "ai": int}
            pivot: dict[str, dict[str, dict]] = defaultdict(
                lambda: defaultdict(lambda: {"count": 0, "ai": 0})
            )
            total_decisions = 0
            ai_decisions = 0

            for dec in all_decisions:
                src_id = seg_to_source.get(dec.segment_id)
                if src_id not in source_ids:
                    continue
                spk = seg_speaker.get(dec.segment_id, "UNKNOWN")
                if speaker_filter != "ALL" and spk != speaker_filter:
                    continue
                pivot[dec.code_id][src_id]["count"] += 1
                if dec.is_ai:
                    pivot[dec.code_id][src_id]["ai"] += 1
                    ai_decisions += 1
                total_decisions += 1

            # Find maximum count for heat-map intensity normalisation
            max_count = max(
                (cell["count"] for code_cells in pivot.values() for cell in code_cells.values()),
                default=1
            ) or 1

            # Build matrix rows
            matrix_rows = []
            for code in codes:
                cells = []
                row_total = 0
                for src in sources:
                    cell_data = pivot[code.id].get(src.id, {"count": 0, "ai": 0})
                    cnt = cell_data["count"]
                    ai_cnt = cell_data["ai"]
                    # Opacity 0.15 → 0.85 scaled to count/max
                    intensity = round(0.15 + 0.70 * (cnt / max_count), 2) if cnt else 0
                    cells.append({
                        "source_id": src.id,
                        "source_title": src.title or src.id,
                        "count": cnt,
                        "ai_count": ai_cnt,
                        "intensity": intensity,
                    })
                    row_total += cnt
                if hide_empty and row_total == 0:
                    continue
                matrix_rows.append({
                    "code_id": code.id,
                    "code_label": code.label,
                    "definition": code.definition,
                    "cells": cells,
                    "total": row_total,
                })

        ctx.update({
            "codes": codes,
            "sources": sources,
            "matrix_rows": matrix_rows,
            "total_decisions": total_decisions,
            "ai_decisions": ai_decisions,
            "speaker_filter": speaker_filter,
            "hide_empty": hide_empty,
        })
        return ctx
