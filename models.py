"""
models.py — SQLAlchemy ORM table definitions
=============================================

These are pure persistence models.  They mirror the domain entities but are
allowed to use mutable fields, nullable columns, and index hints.

The domain entities (frozen dataclasses) are the truth.  These ORM models
are just the storage adapters — they are never returned to the application
layer directly.  Repositories translate between the two.

Schema design notes
-------------------
- Every table uses a TEXT primary key (UUID4 string) for portability.
- Timestamps are stored as ISO-8601 strings so SQLite and PostgreSQL
  both work without dialect-specific types.
- JSON blobs (filters, metadata, examples) are stored as TEXT and
  de-serialised in the repository layer.
- ``Base.metadata.create_all(engine)`` creates all tables on first run.
  In production use Alembic migrations (see docs/ARCHITECTURE.md).
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
#  Project & Corpus
# ─────────────────────────────────────────────


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    corpora: Mapped[list[CorpusRow]] = relationship(
        "CorpusRow", back_populates="project", cascade="all, delete-orphan"
    )
    codes: Mapped[list[CodeRow]] = relationship(
        "CodeRow", back_populates="project", cascade="all, delete-orphan"
    )


class CorpusRow(Base):
    __tablename__ = "corpora"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    filters_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped[ProjectRow] = relationship("ProjectRow", back_populates="corpora")
    sources: Mapped[list[SourceRow]] = relationship(
        "SourceRow", back_populates="corpus", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_corpus_project", "project_id"),)


# ─────────────────────────────────────────────
#  Source & Segment
# ─────────────────────────────────────────────


class SourceRow(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    corpus_id: Mapped[str] = mapped_column(Text, ForeignKey("corpora.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_path: Mapped[str] = mapped_column(Text, default="")
    participant_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    import_metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    corpus: Mapped[CorpusRow] = relationship("CorpusRow", back_populates="sources")
    segments: Mapped[list[SegmentRow]] = relationship(
        "SegmentRow", back_populates="source", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_source_corpus", "corpus_id"),)


class SegmentRow(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, ForeignKey("sources.id"), nullable=False)
    segment_type: Mapped[str] = mapped_column(Text, nullable=False)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    speaker: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    end_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[SourceRow] = relationship("SourceRow", back_populates="segments")
    decisions: Mapped[list[CodingDecisionRow]] = relationship(
        "CodingDecisionRow", back_populates="segment"
    )

    __table_args__ = (
        Index("ix_segment_source", "source_id"),
        Index("ix_segment_embedding", "embedding_id"),
    )


# ─────────────────────────────────────────────
#  Codebook
# ─────────────────────────────────────────────


class CodeRow(Base):
    __tablename__ = "codes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, ForeignKey("projects.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str] = mapped_column(Text, default="")
    inclusion_criteria: Mapped[str] = mapped_column(Text, default="")
    exclusion_criteria: Mapped[str] = mapped_column(Text, default="")
    examples_json: Mapped[str] = mapped_column(Text, default="[]")
    counterexamples_json: Mapped[str] = mapped_column(Text, default="[]")
    category_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deprecated: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)

    project: Mapped[ProjectRow] = relationship("ProjectRow", back_populates="codes")
    decisions: Mapped[list[CodingDecisionRow]] = relationship(
        "CodingDecisionRow", back_populates="code"
    )

    __table_args__ = (
        UniqueConstraint("project_id", "label", name="uq_code_label_per_project"),
        Index("ix_code_project", "project_id"),
    )


class CategoryRow(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, default="")
    theme_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_category_project", "project_id"),)


class ThemeRow(Base):
    __tablename__ = "themes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, default="")
    evidence_summary: Mapped[str] = mapped_column(Text, default="")
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_theme_project", "project_id"),)


# ─────────────────────────────────────────────
#  Coding decisions & memos
# ─────────────────────────────────────────────


class CodingDecisionRow(Base):
    __tablename__ = "coding_decisions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    segment_id: Mapped[str] = mapped_column(Text, ForeignKey("segments.id"), nullable=False)
    code_id: Mapped[str] = mapped_column(Text, ForeignKey("codes.id"), nullable=False)
    analyst: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="")
    is_ai: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    segment: Mapped[SegmentRow] = relationship("SegmentRow", back_populates="decisions")
    code: Mapped[CodeRow] = relationship("CodeRow", back_populates="decisions")

    __table_args__ = (
        Index("ix_decision_segment", "segment_id"),
        Index("ix_decision_code", "code_id"),
    )


class MemoRow(Base):
    __tablename__ = "memos"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_memo_entity", "entity_type", "entity_id"),
        Index("ix_memo_project", "project_id"),
    )


# ─────────────────────────────────────────────
#  AI assistance
# ─────────────────────────────────────────────


class ModelRunRow(Base):
    __tablename__ = "model_runs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_tier: Mapped[str] = mapped_column(Text, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(Text, nullable=False)
    parameters_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    suggestions: Mapped[list[AISuggestionRow]] = relationship(
        "AISuggestionRow", back_populates="run"
    )

    __table_args__ = (Index("ix_run_project", "project_id"),)


class AISuggestionRow(Base):
    __tablename__ = "ai_suggestions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, ForeignKey("model_runs.id"), nullable=False)
    segment_id: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_code_label: Mapped[str] = mapped_column(Text, nullable=False)
    justification: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    run: Mapped[ModelRunRow] = relationship("ModelRunRow", back_populates="suggestions")

    __table_args__ = (
        Index("ix_suggestion_segment", "segment_id"),
        Index("ix_suggestion_run", "run_id"),
    )


# ─────────────────────────────────────────────
#  Clustering
# ─────────────────────────────────────────────


class ClusterRow(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[str] = mapped_column(Text, ForeignKey("model_runs.id"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    segment_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    coherence_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    promoted_to_category_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (Index("ix_cluster_project", "project_id"),)
