"""
document_importer.py — Importer for text documents (.txt, .docx, .pdf)
thematic/infrastructure/importers/document_importer.py

"""
from __future__ import annotations

import logging
from pathlib import Path

from thematic.domain.entities import Segment, Source, SourceType, new_id

logger = logging.getLogger(__name__)

class GenericDocumentImporter:
    """
    Parses plain text, Word documents, and PDFs into domain entities.
    Chunks the text by paragraphs.
    """
    def __init__(self, min_words: int = 3) -> None:
        self._min_words = min_words

    def can_import(self, path: Path) -> bool:
        return path.suffix.lower() in (".txt", ".docx", ".pdf")

    def import_document(self, path: Path, corpus_id: str) -> tuple[Source, list[Segment]]:
        ext = path.suffix.lower()
        text = ""
        
        if ext == ".txt":
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        elif ext == ".docx":
            import docx
            doc = docx.Document(path)
            text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
        elif ext == ".pdf":
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                pages = [page.extract_text() for page in pdf.pages if page.extract_text()]
                text = "\n".join(pages)
        else:
            raise ValueError(f"Unsupported document format: {ext}")

        source_id = new_id()
        words = text.split()
        total_words = len(words)
        
        source = Source(
            id=source_id,
            corpus_id=corpus_id,
            source_type=SourceType.DOCUMENT,
            title=path.name,
            original_path=str(path),
            participant_ids=[],
            import_metadata={"extension": ext},
            word_count=total_words,
        )

        segments = []
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        
        index = 0
        for para in paragraphs:
            para_words = len(para.split())
            if para_words < self._min_words:
                continue
            
            seg = Segment(
                id=new_id(),
                source_id=source_id,
                segment_type="paragraph",
                index=index,
                text=para,
                speaker="DOCUMENT",
                word_count=para_words,
            )
            segments.append(seg)
            index += 1

        return source, segments
