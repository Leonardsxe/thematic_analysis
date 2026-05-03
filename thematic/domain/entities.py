"""
entities.py — Core domain entities
===================================

All entities are immutable frozen dataclasses.  They have zero external
dependencies — no SQLAlchemy, no Streamlit, no model SDK.  Business rules
live here; persistence and presentation are always elsewhere.

Hierarchy
---------
Project
  └── Corpus
        └── Source  (a transcript or document)
              └── Segment  (a speaker turn or paragraph)
                    └── CodingDecision  (code applied to this segment)

Codebook
  └── Code → Category → Theme
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path


# ─────────────────────────────────────────────
#  Enumerations
# ─────────────────────────────────────────────


class SourceType(StrEnum):
    TRANSCRIPT = "transcript"        # from audio-transcriber .transcript.json
    DOCUMENT = "document"            # .pdf / .docx / .txt
    FIELD_NOTE = "field_note"
    MEMO = "memo"


class SegmentType(StrEnum):
    SPEAKER_TURN = "speaker_turn"    # from diarized transcript
    PARAGRAPH = "paragraph"          # from document
    EXCERPT = "excerpt"              # manually created


class CodeRelationType(StrEnum):
    PARENT_CHILD = "parent_child"
    CAUSAL = "causal"
    CONTEXTUAL = "contextual"
    CONTRASTIVE = "contrastive"
    TEMPORAL = "temporal"


class AISuggestionStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVISED = "revised"
    REJECTED = "rejected"


class ModelTier(StrEnum):
    LOCAL_FAST = "local_fast"       # Ollama + small model
    LOCAL_HEAVY = "local_heavy"     # Ollama + Mixtral (university server)
    CLOUD = "cloud"                 # Claude API


# ─────────────────────────────────────────────
#  IDs
# ─────────────────────────────────────────────


def new_id() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ─────────────────────────────────────────────
#  Project & Corpus
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class Project:
    """
    Top-level container for a research project.

    All corpora, sources, codebooks, and analysis artefacts belong to
    exactly one project.  Projects are isolated from each other.

    Attributes
    ----------
    id:          Unique identifier.
    name:        Human-readable project title.
    description: Research question or objective.
    created_at:  Creation timestamp (UTC).
    """

    id: str
    name: str
    description: str
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(cls, name: str, description: str) -> "Project":
        return cls(id=new_id(), name=name, description=description)


@dataclass(frozen=True)
class Corpus:
    """
    A named collection of sources within a project.

    A project may have multiple corpora — e.g. one per research question,
    territory, or participant group.

    Attributes
    ----------
    id:           Unique identifier.
    project_id:   Parent project.
    name:         Corpus label (e.g. "Urban interviews — phase 1").
    filters:      Arbitrary metadata dict for filtering (territory, period, …).
    """

    id: str
    project_id: str
    name: str
    filters: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(cls, project_id: str, name: str, **filters: str) -> "Corpus":
        return cls(id=new_id(), project_id=project_id, name=name, filters=dict(filters))


# ─────────────────────────────────────────────
#  Source & Segment
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class Participant:
    """
    A research participant referenced in one or more transcripts.

    Attributes
    ----------
    id:          Unique identifier.
    project_id:  Parent project.
    pseudonym:   Name used throughout the research.
    metadata:    Arbitrary profile info (age, territory, role, …).
    """

    id: str
    project_id: str
    pseudonym: str
    metadata: dict[str, str] = field(default_factory=dict)

    @classmethod
    def create(cls, project_id: str, pseudonym: str, **meta: str) -> "Participant":
        return cls(id=new_id(), project_id=project_id, pseudonym=pseudonym, metadata=dict(meta))


@dataclass(frozen=True)
class Source:
    """
    One document or transcript within a corpus.

    Attributes
    ----------
    id:              Unique identifier.
    corpus_id:       Parent corpus.
    source_type:     TRANSCRIPT or DOCUMENT.
    title:           Human-readable title.
    original_path:   Path to the original file on disk.
    participant_ids: Participants present in this source.
    import_metadata: Dict with schema_version, transcriber_version, etc.
    word_count:      Approximate word count (for reporting).
    """

    id: str
    corpus_id: str
    source_type: SourceType
    title: str
    original_path: str
    participant_ids: list[str] = field(default_factory=list)
    import_metadata: dict[str, str] = field(default_factory=dict)
    word_count: int = 0
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        corpus_id: str,
        source_type: SourceType,
        title: str,
        original_path: str | Path,
        **meta: str,
    ) -> "Source":
        return cls(
            id=new_id(),
            corpus_id=corpus_id,
            source_type=source_type,
            title=title,
            original_path=str(original_path),
            import_metadata=dict(meta),
        )


@dataclass(frozen=True)
class Segment:
    """
    The atomic unit of analysis — a speaker turn or document paragraph.

    Segments are created during ingestion and are never deleted, only
    superseded by new ingestion versions (tracked via source_version).

    Attributes
    ----------
    id:              Unique identifier.
    source_id:       Parent source.
    segment_type:    SPEAKER_TURN, PARAGRAPH, or EXCERPT.
    index:           Zero-based position within the source.
    text:            Raw text content.
    speaker:         For transcripts: INTERVIEWER / INTERVIEWEE / UNKNOWN.
    start_s:         Start time in seconds (transcripts only).
    end_s:           End time in seconds (transcripts only).
    word_count:      Approximate word count.
    confidence:      Transcription confidence [0, 1] (transcripts only).
    embedding_id:    Reference to vector store entry (set after embedding).
    """

    id: str
    source_id: str
    segment_type: SegmentType
    index: int
    text: str
    speaker: str | None = None
    start_s: float | None = None
    end_s: float | None = None
    word_count: int = 0
    confidence: float | None = None
    embedding_id: str | None = None

    @classmethod
    def from_speaker_turn(
        cls,
        source_id: str,
        index: int,
        text: str,
        speaker: str,
        start_s: float,
        end_s: float,
        confidence: float,
    ) -> "Segment":
        return cls(
            id=new_id(),
            source_id=source_id,
            segment_type=SegmentType.SPEAKER_TURN,
            index=index,
            text=text,
            speaker=speaker,
            start_s=start_s,
            end_s=end_s,
            word_count=len(text.split()),
            confidence=confidence,
        )

    @classmethod
    def from_paragraph(cls, source_id: str, index: int, text: str) -> "Segment":
        return cls(
            id=new_id(),
            source_id=source_id,
            segment_type=SegmentType.PARAGRAPH,
            index=index,
            text=text,
            word_count=len(text.split()),
        )


# ─────────────────────────────────────────────
#  Codebook entities
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class Code:
    """
    The atomic unit of the codebook.

    Attributes
    ----------
    id:                Unique identifier.
    project_id:        Parent project.
    label:             Short code label (e.g. "exclusion_from_spaces").
    definition:        Full definition the analyst will apply.
    inclusion_criteria: What must be present to apply this code.
    exclusion_criteria: What disqualifies a segment.
    examples:          List of exemplar passages.
    counterexamples:   List of passages that look similar but should not receive this code.
    category_id:       Optional parent category.
    is_deprecated:     True when the code is retired but kept for audit.
    version:           Monotonically increasing edit counter.
    """

    id: str
    project_id: str
    label: str
    definition: str
    inclusion_criteria: str = ""
    exclusion_criteria: str = ""
    examples: list[str] = field(default_factory=list)
    counterexamples: list[str] = field(default_factory=list)
    category_id: str | None = None
    is_deprecated: bool = False
    version: int = 1
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(cls, project_id: str, label: str, definition: str) -> "Code":
        return cls(id=new_id(), project_id=project_id, label=label, definition=definition)


@dataclass(frozen=True)
class Category:
    """
    A grouping of related codes — the middle tier of the codebook hierarchy.

    Code → Category → Theme

    Attributes
    ----------
    id:             Unique identifier.
    project_id:     Parent project.
    label:          Category label.
    rationale:      Why these codes belong together.
    theme_id:       Optional parent theme (set when promoted).
    """

    id: str
    project_id: str
    label: str
    rationale: str = ""
    theme_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(cls, project_id: str, label: str, rationale: str = "") -> "Category":
        return cls(id=new_id(), project_id=project_id, label=label, rationale=rationale)


@dataclass(frozen=True)
class Theme:
    """
    A final analytical theme — the top tier of the codebook hierarchy.

    Themes must be evidence-backed: they require a non-empty ``evidence_summary``
    and at least one linked category before they can be published.

    Attributes
    ----------
    id:               Unique identifier.
    project_id:       Parent project.
    label:            Theme label.
    narrative:        Analytical narrative explaining the theme.
    evidence_summary: Concrete excerpt evidence supporting the theme.
    is_published:     True when approved for reporting.
    """

    id: str
    project_id: str
    label: str
    narrative: str = ""
    evidence_summary: str = ""
    is_published: bool = False
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(cls, project_id: str, label: str) -> "Theme":
        return cls(id=new_id(), project_id=project_id, label=label)


@dataclass(frozen=True)
class CodeRelation:
    """
    A directed relationship between two codes.

    Attributes
    ----------
    id:             Unique identifier.
    source_code_id: The originating code.
    target_code_id: The related code.
    relation_type:  Nature of the relationship.
    note:           Free-text explanation.
    """

    id: str
    source_code_id: str
    target_code_id: str
    relation_type: CodeRelationType
    note: str = ""
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        source_code_id: str,
        target_code_id: str,
        relation_type: CodeRelationType,
        note: str = "",
    ) -> "CodeRelation":
        return cls(
            id=new_id(),
            source_code_id=source_code_id,
            target_code_id=target_code_id,
            relation_type=relation_type,
            note=note,
        )


# ─────────────────────────────────────────────
#  Coding decisions & memos
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class CodingDecision:
    """
    The application of one code to one segment by one analyst.

    Multiple codes can be applied to the same segment (multi-coding).
    Every decision is attributed to an analyst and timestamped for audit.

    Attributes
    ----------
    id:           Unique identifier.
    segment_id:   The segment being coded.
    code_id:      The code being applied.
    analyst:      Analyst identifier (name or email).
    note:         Rationale or observation for this specific application.
    is_ai:        True when the decision originated from an AI suggestion
                  that was accepted by a human.
    ai_run_id:    Reference to the ModelRun that produced the suggestion.
    """

    id: str
    segment_id: str
    code_id: str
    analyst: str
    note: str = ""
    is_ai: bool = False
    ai_run_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        segment_id: str,
        code_id: str,
        analyst: str,
        note: str = "",
        is_ai: bool = False,
        ai_run_id: str | None = None,
    ) -> "CodingDecision":
        return cls(
            id=new_id(),
            segment_id=segment_id,
            code_id=code_id,
            analyst=analyst,
            note=note,
            is_ai=is_ai,
            ai_run_id=ai_run_id,
        )


@dataclass(frozen=True)
class Memo:
    """
    A free-form analytical note attached to any entity.

    Memos can be attached to a segment, source, code, or theme to capture
    analytical thinking that doesn't yet have a formal code.

    Attributes
    ----------
    id:          Unique identifier.
    project_id:  Parent project.
    author:      Analyst identifier.
    text:        Memo content.
    entity_type: Type of entity this memo is attached to.
    entity_id:   ID of the attached entity.
    """

    id: str
    project_id: str
    author: str
    text: str
    entity_type: str
    entity_id: str
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        project_id: str,
        author: str,
        text: str,
        entity_type: str,
        entity_id: str,
    ) -> "Memo":
        return cls(
            id=new_id(),
            project_id=project_id,
            author=author,
            text=text,
            entity_type=entity_type,
            entity_id=entity_id,
        )


# ─────────────────────────────────────────────
#  AI assistance tracking
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class ModelRun:
    """
    A record of one LLM inference call — required for reproducibility.

    Every AI suggestion is linked to a ModelRun so that analysts can
    audit which model/version/config produced any given output.

    Attributes
    ----------
    id:              Unique identifier.
    project_id:      Parent project.
    model_name:      e.g. "claude-sonnet-4-6", "mistral:7b".
    model_tier:      LOCAL_FAST, LOCAL_HEAVY, or CLOUD.
    task:            Human-readable description of what was requested.
    prompt_hash:     SHA-256 of the rendered prompt (for dedup detection).
    parameters:      Dict of model parameters used (temperature, etc.).
    """

    id: str
    project_id: str
    model_name: str
    model_tier: ModelTier
    task: str
    prompt_hash: str
    parameters: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        project_id: str,
        model_name: str,
        model_tier: ModelTier,
        task: str,
        prompt_hash: str,
        **params: object,
    ) -> "ModelRun":
        return cls(
            id=new_id(),
            project_id=project_id,
            model_name=model_name,
            model_tier=model_tier,
            task=task,
            prompt_hash=prompt_hash,
            parameters=dict(params),
        )


@dataclass(frozen=True)
class AISuggestion:
    """
    One code suggestion produced by a model for a specific segment.

    Suggestions are never silently adopted — an analyst must explicitly
    accept, revise, or reject each one.

    Attributes
    ----------
    id:           Unique identifier.
    run_id:       Parent ModelRun.
    segment_id:   Segment the suggestion targets.
    suggested_code_label: Label of the suggested code (may not yet exist).
    justification: Model's reasoning for the suggestion.
    confidence:   Model's self-reported confidence [0, 1].
    status:       PENDING → ACCEPTED / REVISED / REJECTED.
    """

    id: str
    run_id: str
    segment_id: str
    suggested_code_label: str
    justification: str
    confidence: float
    status: AISuggestionStatus = AISuggestionStatus.PENDING
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        run_id: str,
        segment_id: str,
        suggested_code_label: str,
        justification: str,
        confidence: float,
    ) -> "AISuggestion":
        return cls(
            id=new_id(),
            run_id=run_id,
            segment_id=segment_id,
            suggested_code_label=suggested_code_label,
            justification=justification,
            confidence=confidence,
        )


# ─────────────────────────────────────────────
#  Clustering
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class Cluster:
    """
    A set of semantically similar segments produced by an embedding + clustering run.

    Clusters are candidate categories — not final themes.  An analyst must
    review, label, and optionally promote a cluster to a Category.

    Attributes
    ----------
    id:              Unique identifier.
    project_id:      Parent project.
    run_id:          The ModelRun (embedding pass) that produced this cluster.
    label:           AI-proposed label (pending analyst confirmation).
    segment_ids:     Segments belonging to this cluster.
    coherence_score: Silhouette or similar internal cluster quality metric.
    is_reviewed:     True once an analyst has reviewed it.
    promoted_to_category_id: Set when the cluster is promoted.
    """

    id: str
    project_id: str
    run_id: str
    label: str
    segment_ids: list[str] = field(default_factory=list)
    coherence_score: float = 0.0
    is_reviewed: bool = False
    promoted_to_category_id: str | None = None
    created_at: datetime = field(default_factory=utcnow)

    @classmethod
    def create(
        cls,
        project_id: str,
        run_id: str,
        label: str,
        segment_ids: list[str],
        coherence_score: float = 0.0,
    ) -> "Cluster":
        return cls(
            id=new_id(),
            project_id=project_id,
            run_id=run_id,
            label=label,
            segment_ids=list(segment_ids),
            coherence_score=coherence_score,
        )


# ─────────────────────────────────────────────
#  Export / reporting value objects
# ─────────────────────────────────────────────


@dataclass(frozen=True)
class EvidenceRow:
    """One row in an evidence matrix (segment × code intersection)."""

    code_label: str
    code_definition: str
    source_title: str
    speaker: str | None
    segment_index: int
    start_s: float | None
    end_s: float | None
    excerpt: str
    analyst: str
    note: str
    is_ai: bool
    decision_timestamp: str


@dataclass(frozen=True)
class EvidenceMatrix:
    """
    Full evidence matrix for export.

    Attributes
    ----------
    project_id:  Parent project.
    rows:        All evidence rows.
    generated_at: Timestamp of export.
    """

    project_id: str
    rows: list[EvidenceRow]
    generated_at: datetime = field(default_factory=utcnow)

    @property
    def code_labels(self) -> list[str]:
        return sorted({r.code_label for r in self.rows})

    @property
    def source_titles(self) -> list[str]:
        return sorted({r.source_title for r in self.rows})