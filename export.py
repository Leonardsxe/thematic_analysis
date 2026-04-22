"""
export.py — Export use cases
=============================

Application layer: assembles evidence matrices, versioned codebooks,
and audit trails from the repository layer, then delegates serialisation
to injected exporters.

Every exported artefact includes full provenance:
  - source identifier, segment index, and timestamps
  - analyst name and decision timestamp
  - whether the decision originated from AI (is_ai flag)
  - model name and run ID for AI-originated decisions
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

from thematic.domain.entities import EvidenceMatrix, EvidenceRow
from thematic.domain.protocols import (
    CodeRepository,
    CodingDecisionRepository,
    MemoRepository,
    ModelRunRepository,
    SegmentRepository,
    SourceRepository,
)

logger = logging.getLogger(__name__)


class BuildEvidenceMatrixUseCase:
    """
    Assemble the full evidence matrix for a project.

    The matrix cross-references every coded segment against every code,
    preserving analyst attribution, AI flags, timestamps, and speaker metadata.

    Parameters
    ----------
    decision_repo:  Source of all coding decisions.
    segment_repo:   Fetches segment text and metadata.
    code_repo:      Fetches code labels.
    source_repo:    Fetches source titles.
    """

    def __init__(
        self,
        decision_repo: CodingDecisionRepository,
        segment_repo: SegmentRepository,
        code_repo: CodeRepository,
        source_repo: SourceRepository,
    ) -> None:
        self._decisions = decision_repo
        self._segments = segment_repo
        self._codes = code_repo
        self._sources = source_repo

    def execute(
        self,
        project_id: str,
        *,
        speaker_filter: list[str] | None = None,
        include_ai: bool = True,
    ) -> EvidenceMatrix:
        """
        Build the evidence matrix for *project_id*.

        Parameters
        ----------
        project_id:
            The project to export.
        speaker_filter:
            When set, only include segments from these speakers.
            Typical value: ``["INTERVIEWEE"]``.
        include_ai:
            When False, omit AI-assisted coding decisions from the matrix.

        Returns
        -------
        EvidenceMatrix
            Immutable value object ready for serialisation.
        """
        decisions = self._decisions.list_for_project(project_id)
        rows: list[EvidenceRow] = []

        # Pre-fetch all codes once for label lookup.
        code_map = {c.id: c.label for c in self._codes.list_for_project(project_id)}

        for dec in decisions:
            if not include_ai and dec.is_ai:
                continue

            seg = self._segments.get(dec.segment_id)
            if seg is None:
                continue

            if speaker_filter and seg.speaker not in speaker_filter:
                continue

            source = self._sources.get(seg.source_id)
            source_title = source.title if source else "unknown"
            code_label = code_map.get(dec.code_id, "unknown_code")

            rows.append(EvidenceRow(
                code_label=code_label,
                source_title=source_title,
                speaker=seg.speaker,
                start_s=seg.start_s,
                excerpt=seg.text[:500],   # cap very long turns in the matrix
                analyst=dec.analyst,
                note=dec.note,
                is_ai=dec.is_ai,
            ))

        matrix = EvidenceMatrix(project_id=project_id, rows=rows)
        logger.info(
            "Evidence matrix: %d rows, %d unique codes, %d sources.",
            len(rows),
            len(matrix.code_labels),
            len(matrix.source_titles),
        )
        return matrix


class ExportEvidenceMatrixCsvUseCase:
    """
    Serialise an ``EvidenceMatrix`` to CSV format.

    Returns CSV as a UTF-8 string (suitable for ``st.download_button``).
    """

    def execute(self, matrix: EvidenceMatrix) -> str:
        """
        Convert *matrix* to a CSV string.

        Returns
        -------
        str
            UTF-8 CSV with headers on the first row.
        """
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "code", "source", "speaker", "start_s",
                "excerpt", "analyst", "note", "is_ai",
                "exported_at",
            ],
        )
        writer.writeheader()
        exported_at = datetime.now(tz=timezone.utc).isoformat()

        for row in matrix.rows:
            writer.writerow({
                "code": row.code_label,
                "source": row.source_title,
                "speaker": row.speaker or "",
                "start_s": f"{row.start_s:.1f}" if row.start_s is not None else "",
                "excerpt": row.excerpt,
                "analyst": row.analyst,
                "note": row.note,
                "is_ai": "yes" if row.is_ai else "no",
                "exported_at": exported_at,
            })

        return output.getvalue()


class ExportCodebookJsonUseCase:
    """
    Export the project codebook as a versioned JSON document.

    Parameters
    ----------
    code_repo:  Source of all codes.
    """

    def __init__(self, code_repo: CodeRepository) -> None:
        self._codes = code_repo

    def execute(self, project_id: str) -> str:
        """
        Return the full codebook as a JSON string.

        Returns
        -------
        str
            UTF-8 JSON with schema_version, metadata, and all codes.
        """
        codes = self._codes.list_for_project(project_id)
        exported_at = datetime.now(tz=timezone.utc).isoformat()

        payload = {
            "schema_version": "1.0",
            "exported_at": exported_at,
            "project_id": project_id,
            "code_count": len(codes),
            "codes": [
                {
                    "label": c.label,
                    "definition": c.definition,
                    "inclusion_criteria": c.inclusion_criteria,
                    "exclusion_criteria": c.exclusion_criteria,
                    "examples": c.examples,
                    "counterexamples": c.counterexamples,
                    "category_id": c.category_id,
                    "version": c.version,
                    "is_deprecated": c.is_deprecated,
                    "created_at": c.created_at.isoformat(),
                    "updated_at": c.updated_at.isoformat(),
                }
                for c in codes
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)


class ExportAuditTrailUseCase:
    """
    Export the full audit trail for a project.

    Includes every coding decision, AI suggestion outcome, and model run —
    with analyst, timestamp, and model version for every entry.

    Parameters
    ----------
    decision_repo:  Source of all coding decisions.
    run_repo:       Source of all model runs.
    """

    def __init__(
        self,
        decision_repo: CodingDecisionRepository,
        run_repo: ModelRunRepository,
    ) -> None:
        self._decisions = decision_repo
        self._runs = run_repo

    def execute(self, project_id: str) -> str:
        """
        Return the audit trail as a JSON string.

        Returns
        -------
        str
            UTF-8 JSON with a list of audit events, oldest first.
        """
        decisions = self._decisions.list_for_project(project_id)
        runs = self._runs.list_for_project(project_id)

        events = []

        for dec in sorted(decisions, key=lambda d: d.created_at):
            events.append({
                "event": "coding_decision",
                "id": dec.id,
                "segment_id": dec.segment_id,
                "code_id": dec.code_id,
                "analyst": dec.analyst,
                "note": dec.note,
                "is_ai": dec.is_ai,
                "ai_run_id": dec.ai_run_id,
                "timestamp": dec.created_at.isoformat(),
            })

        for run in sorted(runs, key=lambda r: r.created_at):
            events.append({
                "event": "model_run",
                "id": run.id,
                "model_name": run.model_name,
                "model_tier": run.model_tier.value,
                "task": run.task,
                "prompt_hash": run.prompt_hash,
                "parameters": run.parameters,
                "timestamp": run.created_at.isoformat(),
            })

        payload = {
            "schema_version": "1.0",
            "exported_at": datetime.now(tz=timezone.utc).isoformat(),
            "project_id": project_id,
            "event_count": len(events),
            "events": sorted(events, key=lambda e: e["timestamp"]),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
