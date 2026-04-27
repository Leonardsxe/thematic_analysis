import os
import tempfile
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from thematic.infrastructure.db.models import Base
from thematic.infrastructure.db.repositories import (
    SqlProjectRepository,
    SqlCorpusRepository,
    SqlSourceRepository,
    SqlSegmentRepository,
    SqlCodeRepository,
    SqlCodingDecisionRepository,
    SqlClusterRepository,
    SqlModelRunRepository,
)
from thematic.domain.entities import Project, Corpus, Source, SourceType, Segment
from thematic.application.coding import ApplyCodeUseCase, CreateCodeUseCase
from thematic.application.clustering import RunClusteringUseCase, ClusteringConfig
from thematic.infrastructure.embeddings.chroma_service import ChromaEmbeddingService

@pytest.fixture(scope="module")
def temp_chroma_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()

def test_full_pipeline_critical_path(db_session, temp_chroma_dir):
    """Integration test that sets up a full project with real embeddings and DB."""
    # 1. Repositories
    project_repo = SqlProjectRepository(db_session)
    corpus_repo = SqlCorpusRepository(db_session)
    source_repo = SqlSourceRepository(db_session)
    segment_repo = SqlSegmentRepository(db_session)
    cluster_repo = SqlClusterRepository(db_session)
    run_repo = SqlModelRunRepository(db_session)
    code_repo = SqlCodeRepository(db_session)
    decision_repo = SqlCodingDecisionRepository(db_session)

    # 2. Setup Base Data
    project = Project.create(name="Integration Project", description="Testing the critical path")
    project_repo.save(project)

    corpus = Corpus.create(project_id=project.id, name="Test Corpus")
    corpus_repo.save(corpus)

    source = Source.create(
        corpus_id=corpus.id,
        source_type=SourceType.DOCUMENT,
        title="Test Document",
        original_path="test.txt",
    )
    source_repo.save(source)

    segments = [
        Segment.from_paragraph(source.id, 0, "The community park needs more resources and maintenance."),
        Segment.from_paragraph(source.id, 1, "We are lacking spaces for children to play safely."),
        Segment.from_paragraph(source.id, 2, "Local governance has ignored our repeated requests for funding."),
        Segment.from_paragraph(source.id, 3, "Education in the neighborhood is improving, but infrastructure lags behind."),
        Segment.from_paragraph(source.id, 4, "The park is a vital hub for our community gatherings."),
        Segment.from_paragraph(source.id, 5, "Without proper funding, the neighborhood cannot fix the broken streetlights.")
    ]
    segment_repo.save_batch(segments)

    # 3. Embeddings using a real tiny model
    embedder = ChromaEmbeddingService(
        persist_path=temp_chroma_dir,
        model_name="all-MiniLM-L6-v2", # Tiny model for speed in tests
        project_id=project.id,
        device="cpu"
    )
    
    pairs = [(s.id, s.text) for s in segments]
    embedder.embed_batch(pairs)
    
    # Check vectors were saved in Chroma
    assert embedder.collection_count() == 6

    # Update segments with embedding ids
    for s in segments:
        segment_repo.update_embedding_id(s.id, s.id)
    db_session.commit()

    # 4. Clustering Pipeline
    use_case = RunClusteringUseCase(
        embedding_service=embedder,
        segment_repo=segment_repo,
        cluster_repo=cluster_repo,
        run_repo=run_repo,
        llm_service=None,  # No AI labels for this test
        config=ClusteringConfig(min_cluster_size=2)
    )
    
    clusters = use_case.execute(project_id=project.id)
    
    # Depending on HDBSCAN output, we might have clusters or noise (-1), but it shouldn't crash.
    assert isinstance(clusters, list)
    
    saved_clusters = cluster_repo.list_for_project(project.id)
    assert len(saved_clusters) == len(clusters)

    # 5. Coding Workflow
    create_use_case = CreateCodeUseCase(code_repo)
    code = create_use_case.execute(
        project_id=project.id, 
        label="community_spaces", 
        definition="References to parks, playgrounds, etc."
    )
    assert code.id is not None
    
    apply_use_case = ApplyCodeUseCase(decision_repo, code_repo, segment_repo)
    apply_use_case.execute(
        segment_id=segments[0].id,
        code_id=code.id,
        analyst="test_bot"
    )
    db_session.commit()

    decisions = decision_repo.list_for_segment(segments[0].id)
    assert len(decisions) == 1
    assert decisions[0].code_id == code.id
    assert decisions[0].analyst == "test_bot"
