"""
ingest.py — Corpus ingestion use cases
=======================================

Application layer: orchestrates domain entities, repositories, and
infrastructure adapters.  Contains zero business rules of its own.

Use cases
---------
IngestTranscriptUseCase   — import .transcript.json from audio-transcriber
IngestDocumentUseCase     — import .txt / .docx / .pdf
RebuildEmbeddingsUseCase  — re-embed all segments for a project
"""

from __future__ import annotations

import logging
from pathlib import Path

from thematic.domain.entities import Corpus, Source, SourceType
from thematic.domain.protocols import (
    CorpusRepository,
    EmbeddingService,
    SegmentRepository,
    SourceRepository,
    TranscriptImporter,
    DocumentImporter,
)

logger = logging.getLogger(__name__)


class IngestTranscriptUseCase:
    """
    Import a ``.transcript.json`` file from the audio-transcriber project
    into a corpus, persist all segments, and compute their embeddings.

    This is the primary ingestion path for interview material.

    Parameters
    ----------
    corpus_repo:      Saves and retrieves corpus entities.
    source_repo:      Saves source metadata.
    segment_repo:     Saves segment entities.
    importer:         Parses the .transcript.json file format.
    embedding_service: Computes and stores vector embeddings.

    Example
    -------
    ::

        use_case = IngestTranscriptUseCase(
            corpus_repo, source_repo, segment_repo, importer, embedder
        )
        source, segments = use_case.execute(
            path=Path("output/interview.transcript.json"),
            corpus_id="corpus-abc",
        )
        print(f"Imported {len(segments)} segments.")
    """

    def __init__(
        self,
        corpus_repo: CorpusRepository,
        source_repo: SourceRepository,
        segment_repo: SegmentRepository,
        importer: TranscriptImporter,
        embedding_service: EmbeddingService,
    ) -> None:
        self._corpus_repo = corpus_repo
        self._source_repo = source_repo
        self._segment_repo = segment_repo
        self._importer = importer
        self._embedder = embedding_service

    def execute(
        self,
        path: Path,
        corpus_id: str,
        *,
        embed: bool = True,
    ) -> tuple[Source, int]:
        """
        Import and optionally embed one transcript file.

        Parameters
        ----------
        path:
            Path to the ``.transcript.json`` file.
        corpus_id:
            The corpus this source belongs to.
        embed:
            When True (default), compute embeddings for all segments after
            import.  Set False to defer embedding to a batch job.

        Returns
        -------
        tuple[Source, int]
            The created Source entity and the count of imported segments.

        Raises
        ------
        ValueError
            If the file is not a supported transcript format.
        FileNotFoundError
            If the file does not exist.
        """
        if not self._importer.can_import(path):
            raise ValueError(
                f"'{path.name}' is not a supported transcript format. "
                "Expected a .transcript.json file from the audio-transcriber project."
            )

        logger.info("Ingesting transcript: %s", path.name)

        # 1. Parse file into domain entities.
        source, segments = self._importer.import_transcript(path, corpus_id)

        # 2. Persist source and segments.
        self._source_repo.save(source)
        self._segment_repo.save_batch(segments)
        logger.info("Saved source '%s' with %d segments.", source.title, len(segments))

        # 3. Compute embeddings (optional — can be deferred to a batch job).
        if embed and segments:
            logger.info("Computing embeddings for %d segments …", len(segments))
            items = [(seg.id, seg.text) for seg in segments]
            embedding_ids = self._embedder.embed_batch(items)

            for seg, emb_id in zip(segments, embedding_ids):
                self._segment_repo.update_embedding_id(seg.id, emb_id)

            logger.info("Embeddings stored.")

        return source, len(segments)

    def execute_batch(
        self,
        paths: list[Path],
        corpus_id: str,
        *,
        embed: bool = True,
    ) -> dict[str, int]:
        """
        Import multiple transcript files into the same corpus.

        Parameters
        ----------
        paths:      List of .transcript.json paths.
        corpus_id:  Target corpus.
        embed:      Compute embeddings after each import.

        Returns
        -------
        dict[str, int]
            Mapping of file name → segment count.  Failed files are included
            with a count of -1 and logged as errors.
        """
        results: dict[str, int] = {}

        for path in paths:
            try:
                _, count = self.execute(path, corpus_id, embed=embed)
                results[path.name] = count
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to import '%s': %s", path.name, exc)
                results[path.name] = -1

        succeeded = sum(1 for v in results.values() if v >= 0)
        logger.info("Batch import: %d/%d files succeeded.", succeeded, len(paths))
        return results


class IngestDocumentUseCase:
    """
    Import a document file (.txt, .docx, .pdf) into a corpus.
    """

    def __init__(
        self,
        corpus_repo: CorpusRepository,
        source_repo: SourceRepository,
        segment_repo: SegmentRepository,
        importer: DocumentImporter,
        embedding_service: EmbeddingService,
    ) -> None:
        self._corpus_repo = corpus_repo
        self._source_repo = source_repo
        self._segment_repo = segment_repo
        self._importer = importer
        self._embedder = embedding_service

    def execute(
        self,
        path: Path,
        corpus_id: str,
        *,
        embed: bool = True,
    ) -> tuple[Source, int]:
        if not self._importer.can_import(path):
            raise ValueError(
                f"'{path.name}' is not a supported document format. "
                "Expected a .txt, .docx, or .pdf file."
            )

        logger.info("Ingesting document: %s", path.name)
        source, segments = self._importer.import_document(path, corpus_id)

        self._source_repo.save(source)
        self._segment_repo.save_batch(segments)
        logger.info("Saved source '%s' with %d segments.", source.title, len(segments))

        if embed and segments:
            logger.info("Computing embeddings for %d segments …", len(segments))
            items = [(seg.id, seg.text) for seg in segments]
            embedding_ids = self._embedder.embed_batch(items)

            for seg, emb_id in zip(segments, embedding_ids):
                self._segment_repo.update_embedding_id(seg.id, emb_id)

            logger.info("Embeddings stored.")

        return source, len(segments)


class RebuildEmbeddingsUseCase:
    """
    Re-compute embeddings for all segments in a project.

    Use this when:
    - You change the embedding model.
    - Embeddings are missing for newly imported segments.
    - You want to refresh a stale vector store.

    Parameters
    ----------
    segment_repo:      Source of all segments.
    embedding_service: Computes new embeddings.
    batch_size:        Number of segments to embed per batch call.
    """

    def __init__(
        self,
        segment_repo: SegmentRepository,
        embedding_service: EmbeddingService,
        batch_size: int = 64,
    ) -> None:
        self._segment_repo = segment_repo
        self._embedder = embedding_service
        self._batch_size = batch_size

    def execute(self, project_id: str) -> int:
        """
        Rebuild all embeddings for *project_id*.

        Returns
        -------
        int
            Number of segments embedded.
        """
        segments = self._segment_repo.list_for_project(project_id)
        total = len(segments)
        logger.info("Rebuilding embeddings for %d segments in project '%s' …", total, project_id)

        embedded = 0
        for i in range(0, total, self._batch_size):
            batch = segments[i : i + self._batch_size]
            items = [(s.id, s.text) for s in batch]
            embedding_ids = self._embedder.embed_batch(items)

            for seg, emb_id in zip(batch, embedding_ids):
                self._segment_repo.update_embedding_id(seg.id, emb_id)
                embedded += 1

            logger.info("  Embedded %d/%d segments.", embedded, total)

        logger.info("Embedding rebuild complete: %d segments.", embedded)
        return embedded
