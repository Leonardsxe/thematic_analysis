"""
test_use_cases.py — Unit tests for application use cases
=========================================================

All tests use mock objects — no DB, no model, no real files needed.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from thematic.application.coding import (
    ApplyCodeUseCase,
    CreateCodeUseCase,
    FindSimilarSegmentsUseCase,
    SuggestCodesUseCase,
)
from thematic.application.ingest import IngestTranscriptUseCase
from thematic.domain.entities import (
    AISuggestion,
    Code,
    CodingDecision,
    Segment,
    SegmentType,
    Source,
    SourceType,
    new_id,
)
from thematic.domain.entities import utcnow


# ─────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────


def _make_segment(text: str = "Texto de ejemplo suficientemente largo.", speaker: str = "INTERVIEWEE") -> Segment:
    return Segment(
        id=new_id(), source_id="src-1",
        segment_type=SegmentType.SPEAKER_TURN,
        index=0, text=text, speaker=speaker,
        start_s=0.0, end_s=10.0,
        word_count=len(text.split()), confidence=0.9,
    )


def _make_source() -> Source:
    return Source(
        id=new_id(), corpus_id="corp-1",
        source_type=SourceType.TRANSCRIPT,
        title="Entrevista test",
        original_path="/audio/test.mp3",
        created_at=utcnow(),
    )


def _make_code(label: str = "exclusion_from_spaces") -> Code:
    return Code.create("proj-1", label, "Test definition.")


# ─────────────────────────────────────────────
#  CreateCodeUseCase
# ─────────────────────────────────────────────


class TestCreateCodeUseCase:
    def test_creates_and_saves_code(self) -> None:
        repo = MagicMock()
        repo.get_by_label.return_value = None

        uc = CreateCodeUseCase(repo)
        code = uc.execute("proj-1", "new_code", "New definition.")

        assert code.label == "new_code"
        repo.save.assert_called_once_with(code)

    def test_raises_if_label_exists(self) -> None:
        repo = MagicMock()
        repo.get_by_label.return_value = _make_code("existing")

        uc = CreateCodeUseCase(repo)
        with pytest.raises(ValueError, match="already exists"):
            uc.execute("proj-1", "existing", "Def.")

    def test_code_has_project_id(self) -> None:
        repo = MagicMock()
        repo.get_by_label.return_value = None

        uc = CreateCodeUseCase(repo)
        code = uc.execute("my-project", "my_code", "Def.")
        assert code.project_id == "my-project"


# ─────────────────────────────────────────────
#  ApplyCodeUseCase
# ─────────────────────────────────────────────


class TestApplyCodeUseCase:
    def _uc(self, segment=None, code=None):
        decision_repo = MagicMock()
        code_repo = MagicMock()
        segment_repo = MagicMock()
        code_repo.get.return_value = code or _make_code()
        segment_repo.get.return_value = segment or _make_segment()
        return ApplyCodeUseCase(decision_repo, code_repo, segment_repo), decision_repo

    def test_creates_decision(self) -> None:
        uc, decision_repo = self._uc()
        decision = uc.execute("seg-1", "code-1", "analyst")

        assert isinstance(decision, CodingDecision)
        assert decision.is_ai is False
        decision_repo.save.assert_called_once()

    def test_raises_if_segment_missing(self) -> None:
        uc, _ = self._uc(segment=None)
        uc._segment_repo.get.return_value = None
        with pytest.raises(ValueError, match="Segment"):
            uc.execute("ghost", "code-1", "analyst")

    def test_raises_if_code_missing(self) -> None:
        uc, _ = self._uc(code=None)
        uc._code_repo.get.return_value = None
        with pytest.raises(ValueError, match="Code"):
            uc.execute("seg-1", "ghost", "analyst")

    def test_note_is_preserved(self) -> None:
        uc, decision_repo = self._uc()
        decision = uc.execute("seg-1", "code-1", "analyst", note="Important passage.")
        assert decision.note == "Important passage."


# ─────────────────────────────────────────────
#  SuggestCodesUseCase
# ─────────────────────────────────────────────


class TestSuggestCodesUseCase:
    def _make_uc(self, llm_response: list[dict] | None = None):
        llm = MagicMock()
        llm.model_name = "mistral:7b"
        llm.suggest_codes.return_value = llm_response if llm_response is not None else [
            {"label": "exclusion_from_spaces", "justification": "Test", "confidence": 0.9, "is_new_code": False},
        ]

        code_repo = MagicMock()
        code_repo.list_for_project.return_value = [_make_code("existing_code")]

        segment_repo = MagicMock()
        segment_repo.get.return_value = _make_segment()

        suggestion_repo = MagicMock()
        run_repo = MagicMock()

        uc = SuggestCodesUseCase(llm, code_repo, segment_repo, suggestion_repo, run_repo)
        return uc, suggestion_repo, run_repo

    def test_returns_suggestions(self) -> None:
        uc, suggestion_repo, _ = self._make_uc()
        suggestions = uc.execute("seg-1", "proj-1", "Community pedagogy")

        assert len(suggestions) == 1
        assert suggestions[0].suggested_code_label == "exclusion_from_spaces"
        assert suggestions[0].confidence == pytest.approx(0.9)

    def test_suggestions_are_persisted(self) -> None:
        uc, suggestion_repo, _ = self._make_uc()
        suggestions = uc.execute("seg-1", "proj-1", "")
        suggestion_repo.save_batch.assert_called_once_with(suggestions)

    def test_model_run_is_saved(self) -> None:
        uc, _, run_repo = self._make_uc()
        uc.execute("seg-1", "proj-1", "")
        run_repo.save.assert_called_once()

    def test_suggestions_start_pending(self) -> None:
        from thematic.domain.entities import AISuggestionStatus
        uc, _, _ = self._make_uc()
        suggestions = uc.execute("seg-1", "proj-1", "")
        for s in suggestions:
            assert s.status == AISuggestionStatus.PENDING

    def test_raises_if_segment_not_found(self) -> None:
        uc, _, _ = self._make_uc()
        uc._segment_repo.get.return_value = None
        with pytest.raises(ValueError, match="Segment"):
            uc.execute("ghost", "proj-1", "")

    def test_empty_llm_response_returns_empty(self) -> None:
        uc, suggestion_repo, _ = self._make_uc(llm_response=[])
        suggestions = uc.execute("seg-1", "proj-1", "")
        assert suggestions == []

    def test_passes_existing_codes_to_llm(self) -> None:
        uc, _, _ = self._make_uc()
        uc.execute("seg-1", "proj-1", "Context text")
        call_kwargs = uc._llm.suggest_codes.call_args
        assert "existing_code" in call_kwargs.kwargs.get("existing_codes", []) or \
               "existing_code" in (call_kwargs.args[1] if len(call_kwargs.args) > 1 else [])


# ─────────────────────────────────────────────
#  FindSimilarSegmentsUseCase
# ─────────────────────────────────────────────


class TestFindSimilarSegmentsUseCase:
    def test_returns_results_with_text(self) -> None:
        embedder = MagicMock()
        embedder.find_similar.return_value = [("seg-001", 0.92), ("seg-002", 0.81)]

        seg_repo = MagicMock()
        seg_repo.get.side_effect = [
            _make_segment("Texto del segmento uno."),
            _make_segment("Texto del segmento dos."),
        ]

        uc = FindSimilarSegmentsUseCase(embedder, seg_repo)
        results = uc.execute("organización comunitaria", top_k=5)

        assert len(results) == 2
        assert results[0]["score"] == pytest.approx(0.92)
        assert "speaker" in results[0]

    def test_missing_segment_is_skipped(self) -> None:
        embedder = MagicMock()
        embedder.find_similar.return_value = [("seg-001", 0.9), ("ghost", 0.8)]

        seg_repo = MagicMock()
        seg_repo.get.side_effect = [_make_segment("Texto."), None]

        uc = FindSimilarSegmentsUseCase(embedder, seg_repo)
        results = uc.execute("query", top_k=5)
        assert len(results) == 1


# ─────────────────────────────────────────────
#  IngestTranscriptUseCase
# ─────────────────────────────────────────────


class TestIngestTranscriptUseCase:
    def _make_uc(self, importer_result=None):
        corpus_repo = MagicMock()
        source_repo = MagicMock()
        segment_repo = MagicMock()
        embedder = MagicMock()
        embedder.embed_batch.return_value = ["emb-1", "emb-2"]

        importer = MagicMock()
        importer.can_import.return_value = True
        importer.import_transcript.return_value = importer_result or (
            _make_source(),
            [_make_segment("Seg 1"), _make_segment("Seg 2")],
        )

        uc = IngestTranscriptUseCase(
            corpus_repo, source_repo, segment_repo, importer, embedder
        )
        return uc, source_repo, segment_repo, embedder

    def test_saves_source_and_segments(self, tmp_path: Path) -> None:
        path = tmp_path / "test.transcript.json"
        path.write_text("{}", encoding="utf-8")
        uc, source_repo, segment_repo, _ = self._make_uc()
        _, count = uc.execute(path, "corpus-1", embed=False)
        source_repo.save.assert_called_once()
        segment_repo.save_batch.assert_called_once()
        assert count == 2

    def test_embed_flag_controls_embedding(self, tmp_path: Path) -> None:
        path = tmp_path / "test.transcript.json"
        path.write_text("{}", encoding="utf-8")

        uc, _, _, embedder = self._make_uc()
        uc.execute(path, "corpus-1", embed=False)
        embedder.embed_batch.assert_not_called()

        uc2, _, _, embedder2 = self._make_uc()
        uc2.execute(path, "corpus-1", embed=True)
        embedder2.embed_batch.assert_called_once()

    def test_raises_for_unsupported_format(self, tmp_path: Path) -> None:
        path = tmp_path / "unsupported.mp3"
        path.write_text("", encoding="utf-8")
        uc, _, _, _ = self._make_uc()
        uc._importer.can_import.return_value = False
        with pytest.raises(ValueError, match="supported transcript format"):
            uc.execute(path, "corpus-1")
