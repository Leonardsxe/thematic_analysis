"""
01_corpus.py — Corpus and project management
============================================

Create projects, create corpora, import transcripts and documents.
This is the entry point for every new research project.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import streamlit as st
from thematic.presentation.translations import ts as t

# ── Infrastructure & Domain ──────────────────────────────────────────────────
from thematic.infrastructure.db.repositories import (
    SqlProjectRepository,
    SqlCorpusRepository,
    SqlSourceRepository,
    SqlSegmentRepository,
)
from thematic.infrastructure.embeddings.chroma_service import ChromaEmbeddingService
from thematic.infrastructure.importers.transcript_importer import TranscriptJsonImporter
from thematic.application.ingest import IngestTranscriptUseCase
from thematic.domain.entities import Project, Corpus

st.set_page_config(page_title=f"{t('nav_corpus')} | {t('nav_title')}", layout="wide")

# ── Helper: DB Session ───────────────────────────────────────────────────────
def get_session():
    factory = st.session_state.get("db_session_factory")
    if factory is None:
        st.error("Database not initialised. Please check app.py.")
        st.stop()
    return factory()

st.title(t('corpus_title'))

tab_projects, tab_import, tab_sources = st.tabs([t('tab_projects'), t('tab_import'), t('tab_sources')])

with tab_projects:
    st.subheader(t('active_project'))
    
    session = get_session()
    project_repo = SqlProjectRepository(session)
    corpus_repo = SqlCorpusRepository(session)

    col_new, col_select = st.columns(2)

    with col_new:
        with st.form("new_project"):
            st.markdown(f"**{t('create_project')}**")
            name = st.text_input(t('name_label'), placeholder="Urban pedagogy study 2026")
            description = st.text_area(
                t('research_question'),
                placeholder="How do community educators navigate institutional exclusion?",
                height=80,
            )
            submitted = st.form_submit_button(t('create_btn'))
            if submitted and name:
                project = Project.create(name, description)
                project_repo.save(project)
                st.session_state["active_project_id"] = project.id
                st.session_state["active_project_name"] = project.name
                st.success(f"Project '{name}' created.")
                st.rerun()

    with col_select:
        st.markdown(f"**{t('select_existing')}**")
        all_projects = project_repo.list_all()
        project_names = [p.name for p in all_projects]
        
        if not project_names:
            st.info("No projects found. Create one first.")
        else:
            chosen_name = st.selectbox(t('nav_corpus'), project_names)
            if st.button(t('activate_btn')):
                chosen_p = next(p for p in all_projects if p.name == chosen_name)
                st.session_state["active_project_id"] = chosen_p.id
                st.session_state["active_project_name"] = chosen_p.name
                st.success(f"Active project: {chosen_p.name}")
                st.rerun()

    if st.session_state.get("active_project_name"):
        st.info(t('active_project_info').format(name=st.session_state['active_project_name']))
        
        # Corpus selection within project
        st.divider()
        project_id = st.session_state["active_project_id"]
        corpora = corpus_repo.list_for_project(project_id)
        
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if corpora:
                c_names = [c.name for c in corpora]
                selected_c = st.selectbox("Corpus", c_names)
                active_c = next(c for c in corpora if c.name == selected_c)
                st.session_state["active_corpus_id"] = active_c.id
                st.session_state["active_corpus_name"] = active_c.name
            else:
                st.warning("No corpora in this project.")
        
        with col_c2:
            new_c_name = st.text_input("New corpus name", placeholder="Phase 1")
            if st.button("Create Corpus") and new_c_name:
                new_c = Corpus.create(project_id, new_c_name)
                corpus_repo.save(new_c)
                st.session_state["active_corpus_id"] = new_c.id
                st.session_state["active_corpus_name"] = new_c.name
                st.success(f"Corpus '{new_c_name}' created.")
                st.rerun()
    
    session.close()

# ── Import ────────────────────────────────────────────────────────────────────
with tab_import:
    st.subheader("Import material")

    import_type = st.radio(
        "Source type",
        ["Transcript (.transcript.json)", "Document (.txt / .docx / .pdf)"],
        horizontal=True,
    )

    uploaded = st.file_uploader(
        "Upload file",
        type=["json", "txt", "docx", "pdf"] if "Document" in import_type else ["json"],
        help=(
            "For transcripts: upload the .transcript.json file produced by the "
            "audio-transcriber project. Speaker labels, timestamps, and "
            "confidence scores are preserved automatically."
        ),
    )

    corpus_name = st.text_input("Corpus name", placeholder="Phase 1 interviews")

    include_interviewer = st.checkbox(
        "Include INTERVIEWER turns",
        value=False,
        help=(
            "By default, only INTERVIEWEE turns are imported for thematic analysis. "
            "Enable this to import all speaker turns."
        ),
    )

    min_words = st.slider(
        "Minimum words per segment",
        min_value=1,
        max_value=20,
        value=3,
        help="Segments shorter than this are skipped (removes filler utterances).",
    )

    if uploaded and st.button("Import"):
        active_corpus_id = st.session_state.get("active_corpus_id")
        if not active_corpus_id:
            st.error("Please select or create a project and corpus first in the 'Projects' tab.")
        else:
            with st.spinner("Importing and computing embeddings…"):
                # Save uploaded file to a temp path with the expected extension.
                with tempfile.NamedTemporaryFile(suffix=".transcript.json", delete=False) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = Path(tmp.name)

                try:
                    session = get_session()
                    
                    # 1. Setup repositories & service
                    source_repo = SqlSourceRepository(session)
                    segment_repo = SqlSegmentRepository(session)
                    corpus_repo = SqlCorpusRepository(session)
                    
                    settings = st.session_state.get("settings")
                    embedder = ChromaEmbeddingService(
                        persist_path=settings.chroma_path,
                        model_name=settings.embedding_model,
                        device=settings.embedding_device,
                    )
                    
                    importer = TranscriptJsonImporter(
                        min_words=min_words,
                        include_interviewer=include_interviewer,
                    )
                    
                    # 2. Setup and run use case
                    use_case = IngestTranscriptUseCase(
                        corpus_repo=corpus_repo,
                        source_repo=source_repo,
                        segment_repo=segment_repo,
                        importer=importer,
                        embedding_service=embedder,
                    )
                    
                    source, count = use_case.execute(tmp_path, active_corpus_id)
                    session.commit()
                    
                    st.success(f"Imported **{source.title}**: {count} segments.")
                    st.balloons()
                    
                    # 3. Show preview of first few segments
                    segs = segment_repo.list_for_source(source.id)
                    with st.expander("Preview first 5 segments"):
                        for seg in segs[:5]:
                            speaker_label = f"**{seg.speaker}**" if seg.speaker else ""
                            time = f"`{seg.start_s:.0f}s`" if seg.start_s is not None else ""
                            st.markdown(f"{speaker_label} {time}  \n{seg.text}")
                            st.divider()

                    # 4. Cleanup temp file
                    tmp_path.unlink()
                except Exception as exc:
                    st.error(f"Import failed: {exc}")
                finally:
                    if 'session' in locals():
                        session.close()

# ── Sources ───────────────────────────────────────────────────────────────────
with tab_sources:
    st.subheader("Imported sources")
    
    active_corpus_id = st.session_state.get("active_corpus_id")
    if not active_corpus_id:
        st.info("Please select a project and corpus to see its sources.")
    else:
        session = get_session()
        source_repo = SqlSourceRepository(session)
        segment_repo = SqlSegmentRepository(session)
        
        sources = source_repo.list_for_corpus(active_corpus_id)
        if not sources:
            st.info("No sources found for this corpus. Import one in the 'Import' tab.")
        else:
            for src in sources:
                segs = segment_repo.list_for_source(src.id)
                word_count = sum(len(s.text.split()) for s in segs)
                
                with st.expander(f"**{src.title}**"):
                    col1, col2, col3 = st.columns(3)
                    col1.write(f"Segments: {len(segs)}")
                    col2.write(f"Words: {word_count}")
                    col3.write(f"Language: {src.import_metadata.get('language', 'unknown')}")
                    
                    st.caption(f"Source ID: {src.id}")
                    if st.button("Delete source", key=f"del_{src.id}"):
                        st.error("Deletion not implemented in UI yet (coming soon).")
        
        session.close()

    st.caption(
        "Each source shows: title · segment count · word count · language"
    )
