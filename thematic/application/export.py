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

        # Pre-fetch all codes once for label and definition lookup.
        codes_list = self._codes.list_for_project(project_id)
        code_label_map = {c.id: c.label for c in codes_list}
        code_def_map   = {c.id: (c.definition or "") for c in codes_list}

        # Track segment index per source for human-readable position
        source_seg_index: dict[str, int] = {}

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
            code_label  = code_label_map.get(dec.code_id, "unknown_code")
            code_def    = code_def_map.get(dec.code_id, "")

            # Segment index per source (1-based, stable within a run)
            key = seg.source_id
            source_seg_index[key] = source_seg_index.get(key, 0) + 1

            rows.append(EvidenceRow(
                code_label=code_label,
                code_definition=code_def,
                source_title=source_title,
                speaker=seg.speaker,
                segment_index=source_seg_index[key],
                start_s=seg.start_s,
                end_s=getattr(seg, "end_s", None),
                excerpt=seg.text[:500],
                analyst=dec.analyst,
                note=dec.note or "",
                is_ai=dec.is_ai,
                decision_timestamp=dec.created_at.isoformat(),
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
                "code", "code_definition",
                "source", "speaker",
                "segment_index", "start_s", "end_s",
                "excerpt", "analyst", "note",
                "is_ai", "decision_timestamp", "exported_at",
            ],
        )
        writer.writeheader()
        exported_at = datetime.now(tz=timezone.utc).isoformat()

        for row in matrix.rows:
            writer.writerow({
                "code":               row.code_label,
                "code_definition":    row.code_definition,
                "source":             row.source_title,
                "speaker":            row.speaker or "",
                "segment_index":      row.segment_index,
                "start_s":            f"{row.start_s:.1f}" if row.start_s is not None else "",
                "end_s":              f"{row.end_s:.1f}"   if row.end_s   is not None else "",
                "excerpt":            row.excerpt,
                "analyst":            row.analyst,
                "note":               row.note or "",
                "is_ai":              "yes" if row.is_ai else "no",
                "decision_timestamp": row.decision_timestamp,
                "exported_at":        exported_at,
            })

        return output.getvalue()


class ExportCodebookMarkdownUseCase:
    """
    Export the codebook as a human-readable Markdown document.

    Suitable for printing, sharing with supervisors, or attaching
    to a methodology appendix without requiring JSON knowledge.
    """

    def __init__(self, code_repo: CodeRepository) -> None:
        self._codes = code_repo

    def execute(self, project_id: str) -> str:
        codes       = self._codes.list_for_project(project_id)
        active      = [c for c in codes if not c.is_deprecated]
        deprecated  = [c for c in codes if c.is_deprecated]
        exported_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            "# Codebook",
            f"",
            f"**Project:** `{project_id}`  ",
            f"**Exported:** {exported_at}  ",
            f"**Codes:** {len(active)} active, {len(deprecated)} deprecated",
            "",
            "---",
            "",
        ]

        # Group by category
        by_category: dict[str | None, list] = {}
        for code in active:
            by_category.setdefault(code.category_id, []).append(code)

        # Uncategorised first
        if None in by_category:
            lines.append("## Uncategorised codes")
            lines.append("")
            for code in by_category[None]:
                lines.extend(_code_to_md(code))

        for cat_id, cat_codes in by_category.items():
            if cat_id is None:
                continue
            lines.append(f"## Category: `{cat_id[:8]}`")
            lines.append("")
            for code in cat_codes:
                lines.extend(_code_to_md(code))

        if deprecated:
            lines.append("---")
            lines.append("## Deprecated codes")
            lines.append("")
            for code in deprecated:
                lines.append(f"- ~~`{code.label}`~~ — {code.definition or 'No definition'}")
            lines.append("")

        return "\n".join(lines)


def _code_to_md(code) -> list[str]:
    lines = [
        f"### `{code.label}`",
        "",
        f"**Definition:** {code.definition or '—'}",
        "",
    ]
    if code.inclusion_criteria:
        lines += [f"**When to apply:** {code.inclusion_criteria}", ""]
    if code.exclusion_criteria:
        lines += [f"**Do not apply when:** {code.exclusion_criteria}", ""]
    if code.examples:
        lines += [f"**Examples:** {code.examples}", ""]
    lines += [f"*Version {code.version} · Created {code.created_at.strftime('%Y-%m-%d')}*", "", "---", ""]
    return lines


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