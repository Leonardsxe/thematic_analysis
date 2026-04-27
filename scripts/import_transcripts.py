#!/usr/bin/env python3
"""
import_transcripts.py — Batch import .transcript.json files into the platform
==============================================================================

Usage
-----
    python scripts/import_transcripts.py ./output --project "Urban pedagogy 2026" --corpus "Phase 1"

    # With DB already initialised:
    python scripts/import_transcripts.py ./output --project-id proj-abc --corpus-id corp-123

Options
-------
    --project      Create or use an existing project by name
    --corpus       Corpus name (created if not exists)
    --include-all  Include both INTERVIEWER and INTERVIEWEE turns (default: INTERVIEWEE only)
    --no-embed     Skip embedding generation (run later with rebuild_embeddings.py)
    --db-url       SQLite or PostgreSQL URL (default: from .env)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the project root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Batch import .transcript.json files from the audio-transcriber project.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_dir", type=Path, help="Directory containing .transcript.json files.")
    parser.add_argument("--project", default="New project", help="Project name to create or use.")
    parser.add_argument("--corpus", default="Corpus", help="Corpus name.")
    parser.add_argument("--include-all", action="store_true",
                        help="Include INTERVIEWER turns (default: INTERVIEWEE only).")
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip embedding generation.")
    parser.add_argument("--min-words", type=int, default=3,
                        help="Minimum words per segment (default: 3).")
    parser.add_argument("--db-url", default=None, help="Database URL (overrides .env).")
    args = parser.parse_args()

    input_dir: Path = args.input_dir
    if not input_dir.is_dir():
        print(f"ERROR: '{input_dir}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    transcript_files = sorted(input_dir.glob("*.transcript.json"))
    if not transcript_files:
        print(f"No .transcript.json files found in '{input_dir}'.", file=sys.stderr)
        sys.exit(1)

    print(f"\nFound {len(transcript_files)} transcript file(s) in '{input_dir}'")
    print(f"Project : {args.project}")
    print(f"Corpus  : {args.corpus}")
    print(f"Speakers: {'ALL' if args.include_all else 'INTERVIEWEE only'}")
    print(f"Embed   : {'NO (deferred)' if args.no_embed else 'YES'}\n")

    # ── Wire dependencies ──────────────────────────────────────────────────────
    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")
        db_url: str = "sqlite:///./thematic.db"
        chroma_path: str = "./chroma_store"
        embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
        embedding_device: str | None = None

    settings = Settings()
    db_url = args.db_url or settings.db_url

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from thematic.infrastructure.db import models as db_models

    engine = create_engine(db_url)
    db_models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    from thematic.infrastructure.db.repositories import (
        SqlCorpusRepository,
        SqlProjectRepository,
        SqlSegmentRepository,
        SqlSourceRepository,
    )
    from thematic.infrastructure.embeddings.chroma_service import ChromaEmbeddingService
    from thematic.infrastructure.importers.transcript_importer import TranscriptJsonImporter
    from thematic.application.ingest import IngestTranscriptUseCase
    from thematic.domain.entities import Corpus, Project

    project_repo = SqlProjectRepository(session)
    corpus_repo = SqlCorpusRepository(session)
    source_repo = SqlSourceRepository(session)
    segment_repo = SqlSegmentRepository(session)
    embedder = ChromaEmbeddingService(
        persist_path=settings.chroma_path,
        model_name=settings.embedding_model,
        device=settings.embedding_device,
    )
    importer = TranscriptJsonImporter(
        min_words=args.min_words,
        include_interviewer=args.include_all,
    )

    # Ensure project + corpus exist.
    existing_projects = project_repo.list_all()
    project = next((p for p in existing_projects if p.name == args.project), None)
    if project is None:
        project = Project.create(args.project, "")
        project_repo.save(project)
        print(f"Created project '{project.name}' (id={project.id})")

    existing_corpora = corpus_repo.list_for_project(project.id)
    corpus = next((c for c in existing_corpora if c.name == args.corpus), None)
    if corpus is None:
        corpus = Corpus.create(project.id, args.corpus)
        corpus_repo.save(corpus)
        print(f"Created corpus '{corpus.name}' (id={corpus.id})")

    # Run ingestion.
    use_case = IngestTranscriptUseCase(corpus_repo, source_repo, segment_repo, importer, embedder)
    results = use_case.execute_batch(
        transcript_files,
        corpus_id=corpus.id,
        embed=not args.no_embed,
    )

    # Report.
    succeeded = sum(1 for v in results.values() if v >= 0)
    total_segs = sum(v for v in results.values() if v >= 0)
    print(f"\n{'─'*50}")
    print(f"  Imported {succeeded}/{len(transcript_files)} files")
    print(f"  Total segments: {total_segs}")
    print(f"  Project: {project.name} ({project.id})")
    print(f"  Corpus:  {corpus.name} ({corpus.id})")
    if args.no_embed:
        print(f"\n  Embeddings deferred. Run:")
        print(f"    python scripts/rebuild_embeddings.py --project-id {project.id}")

    session.close()


if __name__ == "__main__":
    main()