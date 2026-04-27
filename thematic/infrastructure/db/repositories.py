"""
repositories.py — SQLAlchemy repository implementations
=========================================================

Each repository translates between the SQLAlchemy ORM layer (rows) and
the domain entity layer (frozen dataclasses).

Design rules
------------
- Repositories are the ONLY place that imports SQLAlchemy.
- They never return ORM row objects to the application layer.
- They never contain business logic — only reads, writes, and mapping.
- Session lifecycle is managed by the caller (use-case or presentation).

SRP: one class per aggregate root.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from thematic.domain.entities import (
    AISuggestion,
    AISuggestionStatus,
    Category,
    Cluster,
    Code,
    CodingDecision,
    Corpus,
    Memo,
    ModelRun,
    ModelTier,
    Project,
    Segment,
    SegmentType,
    Source,
    SourceType,
    Theme,
)
from thematic.infrastructure.db.models import (
    AISuggestionRow,
    CategoryRow,
    ClusterRow,
    CodeRow,
    CodingDecisionRow,
    CorpusRow,
    MemoRow,
    ModelRunRow,
    ProjectRow,
    SegmentRow,
    SourceRow,
    ThemeRow,
)

logger = logging.getLogger(__name__)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ─────────────────────────────────────────────
#  Project repository
# ─────────────────────────────────────────────


class SqlProjectRepository:
    """Satisfies the ``ProjectRepository`` protocol."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, project: Project) -> None:
        existing = self._s.get(ProjectRow, project.id)
        if existing:
            existing.name = project.name
            existing.description = project.description
        else:
            self._s.add(ProjectRow(
                id=project.id,
                name=project.name,
                description=project.description,
                created_at=_iso(project.created_at),
            ))
        self._s.commit()

    def get(self, project_id: str) -> Project | None:
        row = self._s.get(ProjectRow, project_id)
        return _project_from_row(row) if row else None

    def list_all(self) -> list[Project]:
        rows = self._s.query(ProjectRow).order_by(ProjectRow.created_at.desc()).all()
        return [_project_from_row(r) for r in rows]

    def delete(self, project_id: str) -> None:
        row = self._s.get(ProjectRow, project_id)
        if row:
            self._s.delete(row)
            self._s.commit()


def _project_from_row(r: ProjectRow) -> Project:
    return Project(id=r.id, name=r.name, description=r.description,
                   created_at=_from_iso(r.created_at))


# ─────────────────────────────────────────────
#  Corpus repository
# ─────────────────────────────────────────────


class SqlCorpusRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, corpus: Corpus) -> None:
        existing = self._s.get(CorpusRow, corpus.id)
        if existing:
            existing.name = corpus.name
            existing.filters_json = json.dumps(corpus.filters, ensure_ascii=False)
        else:
            self._s.add(CorpusRow(
                id=corpus.id,
                project_id=corpus.project_id,
                name=corpus.name,
                filters_json=json.dumps(corpus.filters, ensure_ascii=False),
                created_at=_iso(corpus.created_at),
            ))
        self._s.commit()

    def get(self, corpus_id: str) -> Corpus | None:
        row = self._s.get(CorpusRow, corpus_id)
        return _corpus_from_row(row) if row else None

    def list_for_project(self, project_id: str) -> list[Corpus]:
        rows = self._s.query(CorpusRow).filter_by(project_id=project_id).all()
        return [_corpus_from_row(r) for r in rows]


def _corpus_from_row(r: CorpusRow) -> Corpus:
    return Corpus(
        id=r.id, project_id=r.project_id, name=r.name,
        filters=json.loads(r.filters_json or "{}"),
        created_at=_from_iso(r.created_at),
    )


# ─────────────────────────────────────────────
#  Source repository
# ─────────────────────────────────────────────


class SqlSourceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, source: Source) -> None:
        existing = self._s.get(SourceRow, source.id)
        if existing:
            existing.title = source.title
            existing.word_count = source.word_count
            existing.import_metadata_json = json.dumps(source.import_metadata, ensure_ascii=False)
        else:
            self._s.add(SourceRow(
                id=source.id,
                corpus_id=source.corpus_id,
                source_type=source.source_type.value,
                title=source.title,
                original_path=source.original_path,
                participant_ids_json=json.dumps(source.participant_ids),
                import_metadata_json=json.dumps(source.import_metadata, ensure_ascii=False),
                word_count=source.word_count,
                created_at=_iso(source.created_at),
            ))
        self._s.commit()

    def get(self, source_id: str) -> Source | None:
        row = self._s.get(SourceRow, source_id)
        return _source_from_row(row) if row else None

    def list_for_corpus(self, corpus_id: str) -> list[Source]:
        rows = self._s.query(SourceRow).filter_by(corpus_id=corpus_id).all()
        return [_source_from_row(r) for r in rows]

    def count_for_project(self, project_id: str) -> int:
        return (
            self._s.query(SourceRow)
            .join(CorpusRow, SourceRow.corpus_id == CorpusRow.id)
            .filter(CorpusRow.project_id == project_id)
            .count()
        )

    def delete(self, source_id: str) -> None:
        """Delete a source record. Delete its segments first via SqlSegmentRepository."""
        row = self._s.get(SourceRow, source_id)
        if row:
            self._s.delete(row)
            self._s.commit()


def _source_from_row(r: SourceRow) -> Source:
    return Source(
        id=r.id, corpus_id=r.corpus_id,
        source_type=SourceType(r.source_type),
        title=r.title, original_path=r.original_path,
        participant_ids=json.loads(r.participant_ids_json or "[]"),
        import_metadata=json.loads(r.import_metadata_json or "{}"),
        word_count=r.word_count,
        created_at=_from_iso(r.created_at),
    )


# ─────────────────────────────────────────────
#  Segment repository
# ─────────────────────────────────────────────


class SqlSegmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save_batch(self, segments: list[Segment]) -> None:
        for seg in segments:
            if not self._s.get(SegmentRow, seg.id):
                self._s.add(_segment_to_row(seg))
        self._s.commit()

    def get(self, segment_id: str) -> Segment | None:
        row = self._s.get(SegmentRow, segment_id)
        return _segment_from_row(row) if row else None

    def list_for_source(self, source_id: str) -> list[Segment]:
        rows = (self._s.query(SegmentRow)
                .filter_by(source_id=source_id)
                .order_by(SegmentRow.index).all())
        return [_segment_from_row(r) for r in rows]

    def list_for_project(self, project_id: str) -> list[Segment]:
        rows = (
            self._s.query(SegmentRow)
            .join(SourceRow, SegmentRow.source_id == SourceRow.id)
            .join(CorpusRow, SourceRow.corpus_id == CorpusRow.id)
            .filter(CorpusRow.project_id == project_id)
            .order_by(SegmentRow.source_id, SegmentRow.index)
            .all()
        )
        return [_segment_from_row(r) for r in rows]

    def update_embedding_id(self, segment_id: str, embedding_id: str) -> None:
        row = self._s.get(SegmentRow, segment_id)
        if row:
            row.embedding_id = embedding_id
            self._s.commit()

    def delete_for_source(self, source_id: str) -> None:
        """Delete all segments belonging to a source (call before deleting the source)."""
        self._s.query(SegmentRow).filter(SegmentRow.source_id == source_id).delete()

    def count_for_project(self, project_id: str) -> int:
        return (
            self._s.query(SegmentRow)
            .join(SourceRow, SegmentRow.source_id == SourceRow.id)
            .join(CorpusRow, SourceRow.corpus_id == CorpusRow.id)
            .filter(CorpusRow.project_id == project_id)
            .count()
        )


def _segment_to_row(seg: Segment) -> SegmentRow:
    return SegmentRow(
        id=seg.id, source_id=seg.source_id,
        segment_type=seg.segment_type.value,
        index=seg.index, text=seg.text,
        speaker=seg.speaker, start_s=seg.start_s, end_s=seg.end_s,
        word_count=seg.word_count, confidence=seg.confidence,
        embedding_id=seg.embedding_id,
    )


def _segment_from_row(r: SegmentRow) -> Segment:
    return Segment(
        id=r.id, source_id=r.source_id,
        segment_type=SegmentType(r.segment_type),
        index=r.index, text=r.text,
        speaker=r.speaker, start_s=r.start_s, end_s=r.end_s,
        word_count=r.word_count, confidence=r.confidence,
        embedding_id=r.embedding_id,
    )


# ─────────────────────────────────────────────
#  Code repository
# ─────────────────────────────────────────────


class SqlCodeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, code: Code) -> None:
        existing = self._s.get(CodeRow, code.id)
        if existing:
            existing.label = code.label
            existing.definition = code.definition
            existing.inclusion_criteria = code.inclusion_criteria
            existing.exclusion_criteria = code.exclusion_criteria
            existing.examples_json = json.dumps(code.examples, ensure_ascii=False)
            existing.counterexamples_json = json.dumps(code.counterexamples, ensure_ascii=False)
            existing.category_id = code.category_id
            existing.is_deprecated = code.is_deprecated
            existing.version = code.version
            existing.updated_at = _iso(code.updated_at)
        else:
            self._s.add(CodeRow(
                id=code.id, project_id=code.project_id,
                label=code.label, definition=code.definition,
                inclusion_criteria=code.inclusion_criteria,
                exclusion_criteria=code.exclusion_criteria,
                examples_json=json.dumps(code.examples, ensure_ascii=False),
                counterexamples_json=json.dumps(code.counterexamples, ensure_ascii=False),
                category_id=code.category_id,
                is_deprecated=code.is_deprecated,
                version=code.version,
                created_at=_iso(code.created_at),
                updated_at=_iso(code.updated_at),
            ))
        self._s.commit()

    def get(self, code_id: str) -> Code | None:
        row = self._s.get(CodeRow, code_id)
        return _code_from_row(row) if row else None

    def get_by_label(self, project_id: str, label: str) -> Code | None:
        row = (self._s.query(CodeRow)
               .filter_by(project_id=project_id, label=label).first())
        return _code_from_row(row) if row else None

    def list_for_project(self, project_id: str) -> list[Code]:
        rows = (self._s.query(CodeRow)
                .filter_by(project_id=project_id, is_deprecated=False)
                .order_by(CodeRow.label).all())
        return [_code_from_row(r) for r in rows]

    def delete(self, code_id: str) -> None:
        row = self._s.get(CodeRow, code_id)
        if row:
            self._s.delete(row)
            self._s.commit()


def _code_from_row(r: CodeRow) -> Code:
    return Code(
        id=r.id, project_id=r.project_id, label=r.label,
        definition=r.definition,
        inclusion_criteria=r.inclusion_criteria,
        exclusion_criteria=r.exclusion_criteria,
        examples=json.loads(r.examples_json or "[]"),
        counterexamples=json.loads(r.counterexamples_json or "[]"),
        category_id=r.category_id,
        is_deprecated=r.is_deprecated,
        version=r.version,
        created_at=_from_iso(r.created_at),
        updated_at=_from_iso(r.updated_at),
    )


# ─────────────────────────────────────────────
#  Coding decision repository
# ─────────────────────────────────────────────


class SqlCodingDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, decision: CodingDecision) -> None:
        if not self._s.get(CodingDecisionRow, decision.id):
            self._s.add(CodingDecisionRow(
                id=decision.id, segment_id=decision.segment_id,
                code_id=decision.code_id, analyst=decision.analyst,
                note=decision.note, is_ai=decision.is_ai,
                ai_run_id=decision.ai_run_id,
                created_at=_iso(decision.created_at),
            ))
            self._s.commit()

    def list_for_segment(self, segment_id: str) -> list[CodingDecision]:
        rows = self._s.query(CodingDecisionRow).filter_by(segment_id=segment_id).all()
        return [_decision_from_row(r) for r in rows]

    def list_for_code(self, code_id: str) -> list[CodingDecision]:
        rows = self._s.query(CodingDecisionRow).filter_by(code_id=code_id).all()
        return [_decision_from_row(r) for r in rows]

    def list_for_project(self, project_id: str) -> list[CodingDecision]:
        rows = (
            self._s.query(CodingDecisionRow)
            .join(SegmentRow, CodingDecisionRow.segment_id == SegmentRow.id)
            .join(SourceRow, SegmentRow.source_id == SourceRow.id)
            .join(CorpusRow, SourceRow.corpus_id == CorpusRow.id)
            .filter(CorpusRow.project_id == project_id)
            .all()
        )
        return [_decision_from_row(r) for r in rows]

    def delete(self, decision_id: str) -> None:
        row = self._s.get(CodingDecisionRow, decision_id)
        if row:
            self._s.delete(row)
            self._s.commit()


def _decision_from_row(r: CodingDecisionRow) -> CodingDecision:
    return CodingDecision(
        id=r.id, segment_id=r.segment_id, code_id=r.code_id,
        analyst=r.analyst, note=r.note, is_ai=r.is_ai,
        ai_run_id=r.ai_run_id, created_at=_from_iso(r.created_at),
    )


# ─────────────────────────────────────────────
#  Memo repository
# ─────────────────────────────────────────────


class SqlMemoRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, memo: Memo) -> None:
        if not self._s.get(MemoRow, memo.id):
            self._s.add(MemoRow(
                id=memo.id, project_id=memo.project_id,
                author=memo.author, text=memo.text,
                entity_type=memo.entity_type, entity_id=memo.entity_id,
                created_at=_iso(memo.created_at),
            ))
            self._s.commit()

    def list_for_entity(self, entity_type: str, entity_id: str) -> list[Memo]:
        rows = self._s.query(MemoRow).filter_by(
            entity_type=entity_type, entity_id=entity_id
        ).order_by(MemoRow.created_at).all()
        return [_memo_from_row(r) for r in rows]

    def list_for_project(self, project_id: str) -> list[Memo]:
        rows = self._s.query(MemoRow).filter_by(project_id=project_id).all()
        return [_memo_from_row(r) for r in rows]


def _memo_from_row(r: MemoRow) -> Memo:
    return Memo(
        id=r.id, project_id=r.project_id, author=r.author,
        text=r.text, entity_type=r.entity_type, entity_id=r.entity_id,
        created_at=_from_iso(r.created_at),
    )


# ─────────────────────────────────────────────
#  ModelRun & AISuggestion repositories
# ─────────────────────────────────────────────


class SqlModelRunRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save(self, run: ModelRun) -> None:
        if not self._s.get(ModelRunRow, run.id):
            self._s.add(ModelRunRow(
                id=run.id, project_id=run.project_id,
                model_name=run.model_name,
                model_tier=run.model_tier.value,
                task=run.task, prompt_hash=run.prompt_hash,
                parameters_json=json.dumps(run.parameters, ensure_ascii=False),
                created_at=_iso(run.created_at),
            ))
            self._s.commit()

    def get(self, run_id: str) -> ModelRun | None:
        row = self._s.get(ModelRunRow, run_id)
        return _run_from_row(row) if row else None

    def list_for_project(self, project_id: str) -> list[ModelRun]:
        rows = (self._s.query(ModelRunRow)
                .filter_by(project_id=project_id)
                .order_by(ModelRunRow.created_at.desc()).all())
        return [_run_from_row(r) for r in rows]


def _run_from_row(r: ModelRunRow) -> ModelRun:
    return ModelRun(
        id=r.id, project_id=r.project_id,
        model_name=r.model_name,
        model_tier=ModelTier(r.model_tier),
        task=r.task, prompt_hash=r.prompt_hash,
        parameters=json.loads(r.parameters_json or "{}"),
        created_at=_from_iso(r.created_at),
    )


class SqlAISuggestionRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, suggestion_id: str) -> AISuggestion | None:
        row = self._s.get(AISuggestionRow, suggestion_id)
        return _suggestion_from_row(row) if row else None

    def save_batch(self, suggestions: list[AISuggestion]) -> None:
        for s in suggestions:
            if not self._s.get(AISuggestionRow, s.id):
                self._s.add(AISuggestionRow(
                    id=s.id, run_id=s.run_id, segment_id=s.segment_id,
                    suggested_code_label=s.suggested_code_label,
                    justification=s.justification, confidence=s.confidence,
                    status=s.status.value,
                    created_at=_iso(s.created_at),
                ))
        self._s.commit()

    def list_for_segment(self, segment_id: str) -> list[AISuggestion]:
        rows = self._s.query(AISuggestionRow).filter_by(segment_id=segment_id).all()
        return [_suggestion_from_row(r) for r in rows]

    def list_pending_for_project(self, project_id: str) -> list[AISuggestion]:
        rows = (
            self._s.query(AISuggestionRow)
            .join(ModelRunRow, AISuggestionRow.run_id == ModelRunRow.id)
            .filter(ModelRunRow.project_id == project_id)
            .filter(AISuggestionRow.status == "pending")
            .all()
        )
        return [_suggestion_from_row(r) for r in rows]

    def update_status(self, suggestion_id: str, status: str) -> None:
        row = self._s.get(AISuggestionRow, suggestion_id)
        if row:
            row.status = status
            self._s.commit()


def _suggestion_from_row(r: AISuggestionRow) -> AISuggestion:
    return AISuggestion(
        id=r.id, run_id=r.run_id, segment_id=r.segment_id,
        suggested_code_label=r.suggested_code_label,
        justification=r.justification, confidence=r.confidence,
        status=AISuggestionStatus(r.status),
        created_at=_from_iso(r.created_at),
    )


# ─────────────────────────────────────────────
#  Cluster repository
# ─────────────────────────────────────────────


class SqlClusterRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def save_batch(self, clusters: list[Cluster]) -> None:
        for c in clusters:
            if not self._s.get(ClusterRow, c.id):
                self._s.add(ClusterRow(
                    id=c.id, project_id=c.project_id, run_id=c.run_id,
                    label=c.label,
                    segment_ids_json=json.dumps(c.segment_ids),
                    coherence_score=c.coherence_score,
                    is_reviewed=c.is_reviewed,
                    promoted_to_category_id=c.promoted_to_category_id,
                    created_at=_iso(c.created_at),
                ))
        self._s.commit()

    def list_for_project(self, project_id: str) -> list[Cluster]:
        rows = self._s.query(ClusterRow).filter_by(project_id=project_id).all()
        return [_cluster_from_row(r) for r in rows]

    def get(self, cluster_id: str) -> Cluster | None:
        row = self._s.get(ClusterRow, cluster_id)
        return _cluster_from_row(row) if row else None

    def mark_reviewed(self, cluster_id: str, category_id: str | None) -> None:
        row = self._s.get(ClusterRow, cluster_id)
        if row:
            row.is_reviewed = True
            row.promoted_to_category_id = category_id
            self._s.commit()


def _cluster_from_row(r: ClusterRow) -> Cluster:
    return Cluster(
        id=r.id, project_id=r.project_id, run_id=r.run_id,
        label=r.label,
        segment_ids=json.loads(r.segment_ids_json or "[]"),
        coherence_score=r.coherence_score,
        is_reviewed=r.is_reviewed,
        promoted_to_category_id=r.promoted_to_category_id,
        created_at=_from_iso(r.created_at),
    )