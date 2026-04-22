"""
protocols.py — All structural interfaces for the thematic analysis platform
============================================================================

Dependency-Inversion Principle: every layer depends on these abstractions,
never on concrete implementations.  Swap Ollama for Claude, SQLite for
PostgreSQL, or ChromaDB for FAISS — without touching domain or application code.

Interface groups
----------------
Repositories      — persist and retrieve domain entities
EmbeddingService  — compute and retrieve vector embeddings
LLMService        — call a language model for AI assistance
Importers         — parse external file formats into domain entities
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from thematic.domain.entities import (
    AISuggestion,
    Cluster,
    Code,
    Category,
    CodingDecision,
    Corpus,
    EvidenceMatrix,
    Memo,
    ModelRun,
    Participant,
    Project,
    Segment,
    Source,
    Theme,
)


# ─────────────────────────────────────────────
#  Repository protocols
# ─────────────────────────────────────────────


@runtime_checkable
class ProjectRepository(Protocol):
    def save(self, project: Project) -> None: ...
    def get(self, project_id: str) -> Project | None: ...
    def list_all(self) -> list[Project]: ...
    def delete(self, project_id: str) -> None: ...


@runtime_checkable
class CorpusRepository(Protocol):
    def save(self, corpus: Corpus) -> None: ...
    def get(self, corpus_id: str) -> Corpus | None: ...
    def list_for_project(self, project_id: str) -> list[Corpus]: ...


@runtime_checkable
class SourceRepository(Protocol):
    def save(self, source: Source) -> None: ...
    def get(self, source_id: str) -> Source | None: ...
    def list_for_corpus(self, corpus_id: str) -> list[Source]: ...
    def count_for_project(self, project_id: str) -> int: ...


@runtime_checkable
class SegmentRepository(Protocol):
    def save_batch(self, segments: list[Segment]) -> None: ...
    def get(self, segment_id: str) -> Segment | None: ...
    def list_for_source(self, source_id: str) -> list[Segment]: ...
    def list_for_project(self, project_id: str) -> list[Segment]: ...
    def update_embedding_id(self, segment_id: str, embedding_id: str) -> None: ...
    def count_for_project(self, project_id: str) -> int: ...


@runtime_checkable
class CodeRepository(Protocol):
    def save(self, code: Code) -> None: ...
    def get(self, code_id: str) -> Code | None: ...
    def get_by_label(self, project_id: str, label: str) -> Code | None: ...
    def list_for_project(self, project_id: str) -> list[Code]: ...
    def delete(self, code_id: str) -> None: ...


@runtime_checkable
class CodingDecisionRepository(Protocol):
    def save(self, decision: CodingDecision) -> None: ...
    def list_for_segment(self, segment_id: str) -> list[CodingDecision]: ...
    def list_for_code(self, code_id: str) -> list[CodingDecision]: ...
    def list_for_project(self, project_id: str) -> list[CodingDecision]: ...
    def delete(self, decision_id: str) -> None: ...


@runtime_checkable
class MemoRepository(Protocol):
    def save(self, memo: Memo) -> None: ...
    def list_for_entity(self, entity_type: str, entity_id: str) -> list[Memo]: ...
    def list_for_project(self, project_id: str) -> list[Memo]: ...


@runtime_checkable
class ClusterRepository(Protocol):
    def save_batch(self, clusters: list[Cluster]) -> None: ...
    def list_for_project(self, project_id: str) -> list[Cluster]: ...
    def get(self, cluster_id: str) -> Cluster | None: ...
    def mark_reviewed(self, cluster_id: str, category_id: str | None) -> None: ...


@runtime_checkable
class ModelRunRepository(Protocol):
    def save(self, run: ModelRun) -> None: ...
    def get(self, run_id: str) -> ModelRun | None: ...
    def list_for_project(self, project_id: str) -> list[ModelRun]: ...


@runtime_checkable
class AISuggestionRepository(Protocol):
    def save_batch(self, suggestions: list[AISuggestion]) -> None: ...
    def list_for_segment(self, segment_id: str) -> list[AISuggestion]: ...
    def list_pending_for_project(self, project_id: str) -> list[AISuggestion]: ...
    def update_status(self, suggestion_id: str, status: str) -> None: ...


# ─────────────────────────────────────────────
#  Embedding service protocol
# ─────────────────────────────────────────────


@runtime_checkable
class EmbeddingService(Protocol):
    """
    Compute and retrieve dense vector embeddings for text segments.

    The store is keyed by ``embedding_id`` (the ID returned when the
    embedding is saved).  Retrieval returns IDs of similar segments.
    """

    def embed_and_store(self, segment_id: str, text: str) -> str:
        """
        Compute the embedding for *text* and store it.

        Returns
        -------
        str
            The ``embedding_id`` to be stored on the ``Segment``.
        """
        ...

    def embed_batch(self, items: list[tuple[str, str]]) -> list[str]:
        """
        Embed and store multiple (segment_id, text) pairs.

        Returns list of embedding_ids in the same order as *items*.
        """
        ...

    def find_similar(
        self,
        query_text: str,
        top_k: int = 10,
        project_id: str | None = None,
    ) -> list[tuple[str, float]]:
        """
        Return (segment_id, score) pairs for the most similar segments.

        Parameters
        ----------
        query_text:  Query string to embed and compare.
        top_k:       Number of results to return.
        project_id:  When set, restrict results to this project's segments.
        """
        ...

    def get_all_embeddings(self, project_id: str) -> list[tuple[str, list[float]]]:
        """
        Return all (segment_id, vector) pairs for a project.

        Used by clustering pipelines that need the full embedding matrix.
        """
        ...


# ─────────────────────────────────────────────
#  LLM service protocol
# ─────────────────────────────────────────────


@runtime_checkable
class LLMService(Protocol):
    """
    Call a language model for AI-assisted qualitative analysis tasks.

    All methods return structured data (dicts / lists), never raw text,
    so callers can parse results without regex.

    Every call must be traceable: the implementation is responsible for
    creating a ``ModelRun`` record before returning.
    """

    @property
    def model_name(self) -> str:
        """Identifier of the model in use, e.g. ``"claude-sonnet-4-6"``."""
        ...

    def suggest_codes(
        self,
        segment_text: str,
        existing_codes: list[str],
        codebook_context: str,
        project_id: str,
    ) -> list[dict[str, object]]:
        """
        Suggest codes for one segment.

        Returns
        -------
        list[dict]
            Each dict: {label, justification, confidence, is_new_code}.
        """
        ...

    def find_similar_excerpts(
        self,
        reference_text: str,
        candidate_texts: list[str],
    ) -> list[dict[str, object]]:
        """
        Identify which candidates are thematically similar to *reference_text*.

        Returns
        -------
        list[dict]
            Each dict: {index, similarity_reason, relevance_score}.
        """
        ...

    def propose_cluster_label(
        self,
        excerpts: list[str],
        existing_categories: list[str],
    ) -> dict[str, object]:
        """
        Propose a category label for a cluster of excerpts.

        Returns
        -------
        dict
            {label, rationale, contradictions, confidence}.
        """
        ...

    def synthesize_theme(
        self,
        category_labels: list[str],
        supporting_excerpts: list[str],
        project_context: str,
    ) -> dict[str, object]:
        """
        Draft a theme narrative from categories and evidence.

        Returns
        -------
        dict
            {theme_label, narrative, evidence_summary, gaps}.
        """
        ...

    def surface_contradictions(
        self,
        excerpts_by_source: dict[str, list[str]],
        research_question: str,
    ) -> list[dict[str, object]]:
        """
        Identify divergences across sources.

        Returns
        -------
        list[dict]
            Each dict: {source_a, source_b, excerpt_a, excerpt_b, contradiction_note}.
        """
        ...


# ─────────────────────────────────────────────
#  Importer protocols
# ─────────────────────────────────────────────


@runtime_checkable
class TranscriptImporter(Protocol):
    """
    Parse a ``.transcript.json`` from the audio-transcriber project into
    domain entities ready for persistence.
    """

    def can_import(self, path: Path) -> bool:
        """Return True if this importer handles the file at *path*."""
        ...

    def import_transcript(
        self,
        path: Path,
        corpus_id: str,
    ) -> tuple[Source, list[Segment]]:
        """
        Parse *path* and return (Source, [Segment, …]).

        Raises
        ------
        ValueError
            If the file is not a valid transcript JSON.
        """
        ...


@runtime_checkable
class DocumentImporter(Protocol):
    """Parse a text document (.txt, .docx, .pdf) into domain entities."""

    def can_import(self, path: Path) -> bool: ...

    def import_document(
        self,
        path: Path,
        corpus_id: str,
    ) -> tuple[Source, list[Segment]]:
        """Parse *path* and return (Source, [Segment, …])."""
        ...


# ─────────────────────────────────────────────
#  Export protocol
# ─────────────────────────────────────────────


@runtime_checkable
class EvidenceExporter(Protocol):
    """Write an ``EvidenceMatrix`` to disk in a specific format."""

    def export(self, matrix: EvidenceMatrix, destination: Path) -> Path:
        """
        Persist *matrix* and return the path of the written file.
        """
        ...
