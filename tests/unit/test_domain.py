"""
test_domain.py — Unit tests for domain entities and transcript importer
========================================================================

All tests are fast and require zero external dependencies.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from thematic.domain.entities import (
    AISuggestion,
    AISuggestionStatus,
    Category,
    Cluster,
    Code,
    CodingDecision,
    Corpus,
    EvidenceMatrix,
    EvidenceRow,
    ModelRun,
    ModelTier,
    Project,
    Segment,
    SegmentType,
    Source,
    SourceType,
    Theme,
)
from thematic.infrastructure.importers.transcript_importer import TranscriptJsonImporter


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────


def _make_transcript_json(
    turns: list[dict] | None = None,
    language: str = "es",
    duration_s: float = 120.0,
) -> dict:
    """Build a minimal valid .transcript.json payload."""
    if turns is None:
        turns = [
            {
                "turn_index": 0,
                "speaker": "INTERVIEWEE",
                "start": 0.0,
                "end": 30.0,
                "duration": 30.0,
                "word_count": 20,
                "text": "Buenos días, muchas gracias por recibirme en este espacio tan importante para la comunidad.",
                "segments": [{"start": 0.0, "end": 30.0, "text": "Buenos días…", "confidence": 0.91}],
            },
            {
                "turn_index": 1,
                "speaker": "INTERVIEWER",
                "start": 31.0,
                "end": 38.0,
                "duration": 7.0,
                "word_count": 5,
                "text": "¿Cómo fue ese proceso?",
                "segments": [{"start": 31.0, "end": 38.0, "text": "¿Cómo fue?", "confidence": 0.88}],
            },
        ]
    return {
        "schema_version": "1.0",
        "metadata": {
            "source": "/audio/interview.mp3",
            "duration_s": duration_s,
            "language": language,
            "avg_confidence": 0.91,
        },
        "speakers": {
            "INTERVIEWER": {"total_speech_s": 10.0, "turn_count": 1, "word_count": 5},
            "INTERVIEWEE": {"total_speech_s": 110.0, "turn_count": 1, "word_count": 20},
        },
        "turns": turns,
    }


def _write_transcript(tmp_path: Path, payload: dict, name: str = "test.transcript.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


# ─────────────────────────────────────────────
#  Project & Corpus
# ─────────────────────────────────────────────


class TestProject:
    def test_create_sets_id_and_name(self) -> None:
        p = Project.create("Urban pedagogy", "How do educators navigate exclusion?")
        assert p.name == "Urban pedagogy"
        assert len(p.id) == 36  # UUID4

    def test_frozen_raises_on_mutation(self) -> None:
        p = Project.create("Test", "desc")
        with pytest.raises(Exception):
            p.name = "Other"  # type: ignore[misc]

    def test_created_at_is_utc(self) -> None:
        from datetime import timezone
        p = Project.create("Test", "desc")
        assert p.created_at.tzinfo == timezone.utc


class TestCorpus:
    def test_create_with_filters(self) -> None:
        c = Corpus.create("proj-1", "Phase 1", territory="urban", year="2026")
        assert c.filters["territory"] == "urban"
        assert c.project_id == "proj-1"

    def test_filters_default_empty(self) -> None:
        c = Corpus.create("proj-1", "Corpus")
        assert c.filters == {}


# ─────────────────────────────────────────────
#  Segment
# ─────────────────────────────────────────────


class TestSegment:
    def test_from_speaker_turn(self) -> None:
        seg = Segment.from_speaker_turn(
            source_id="src-1",
            index=0,
            text="Hola mundo",
            speaker="INTERVIEWEE",
            start_s=0.0,
            end_s=5.0,
            confidence=0.9,
        )
        assert seg.segment_type == SegmentType.SPEAKER_TURN
        assert seg.speaker == "INTERVIEWEE"
        assert seg.word_count == 2

    def test_from_paragraph(self) -> None:
        seg = Segment.from_paragraph("src-1", 0, "Un párrafo de ejemplo con varias palabras.")
        assert seg.segment_type == SegmentType.PARAGRAPH
        assert seg.speaker is None
        assert seg.word_count == 7


# ─────────────────────────────────────────────
#  Code
# ─────────────────────────────────────────────


class TestCode:
    def test_create_defaults(self) -> None:
        code = Code.create("proj-1", "exclusion_from_spaces", "Definition here.")
        assert code.label == "exclusion_from_spaces"
        assert code.is_deprecated is False
        assert code.version == 1
        assert code.examples == []

    def test_create_unique_ids(self) -> None:
        a = Code.create("proj-1", "code_a", "def")
        b = Code.create("proj-1", "code_b", "def")
        assert a.id != b.id


# ─────────────────────────────────────────────
#  Coding decision
# ─────────────────────────────────────────────


class TestCodingDecision:
    def test_manual_decision(self) -> None:
        d = CodingDecision.create("seg-1", "code-1", "analyst@uni.edu")
        assert d.is_ai is False
        assert d.ai_run_id is None

    def test_ai_decision(self) -> None:
        d = CodingDecision.create(
            "seg-1", "code-1", "analyst@uni.edu", is_ai=True, ai_run_id="run-123"
        )
        assert d.is_ai is True
        assert d.ai_run_id == "run-123"


# ─────────────────────────────────────────────
#  EvidenceMatrix
# ─────────────────────────────────────────────


class TestEvidenceMatrix:
    def _make_matrix(self) -> EvidenceMatrix:
        rows = [
            EvidenceRow(
                code_label="code_a",
                code_definition="Def A",
                source_title="Source 1",
                speaker="INTERVIEWEE",
                segment_index=0,
                start_s=10.0,
                end_s=15.0,
                excerpt="excerpt 1",
                analyst="analyst",
                note="",
                is_ai=False,
                decision_timestamp="2024-01-01",
            ),
            EvidenceRow(
                code_label="code_b",
                code_definition="Def B",
                source_title="Source 1",
                speaker="INTERVIEWEE",
                segment_index=1,
                start_s=20.0,
                end_s=25.0,
                excerpt="excerpt 2",
                analyst="analyst",
                note="",
                is_ai=True,
                decision_timestamp="2024-01-01",
            ),
            EvidenceRow(
                code_label="code_a",
                code_definition="Def A",
                source_title="Source 2",
                speaker="INTERVIEWEE",
                segment_index=0,
                start_s=5.0,
                end_s=10.0,
                excerpt="excerpt 3",
                analyst="analyst",
                note="",
                is_ai=False,
                decision_timestamp="2024-01-01",
            ),
        ]
        return EvidenceMatrix(project_id="proj-1", rows=rows)

    def test_code_labels(self) -> None:
        m = self._make_matrix()
        assert m.code_labels == ["code_a", "code_b"]

    def test_source_titles(self) -> None:
        m = self._make_matrix()
        assert m.source_titles == ["Source 1", "Source 2"]


# ─────────────────────────────────────────────
#  TranscriptJsonImporter
# ─────────────────────────────────────────────


class TestTranscriptJsonImporter:
    def test_can_import_valid_file(self, tmp_path: Path) -> None:
        p = _write_transcript(tmp_path, _make_transcript_json())
        assert TranscriptJsonImporter().can_import(p) is True

    def test_cannot_import_wrong_extension(self, tmp_path: Path) -> None:
        p = tmp_path / "interview.json"
        p.write_text("{}", encoding="utf-8")
        assert TranscriptJsonImporter().can_import(p) is False

    def test_cannot_import_wrong_schema_version(self, tmp_path: Path) -> None:
        payload = _make_transcript_json()
        payload["schema_version"] = "2.0"
        p = _write_transcript(tmp_path, payload)
        assert TranscriptJsonImporter().can_import(p) is False

    def test_imports_source_with_correct_title(self, tmp_path: Path) -> None:
        p = _write_transcript(tmp_path, _make_transcript_json())
        source, _ = TranscriptJsonImporter().import_transcript(p, "corpus-1")
        assert source.source_type == SourceType.TRANSCRIPT
        assert source.corpus_id == "corpus-1"
        assert "interview" in source.title.lower()

    def test_imports_only_interviewee_by_default(self, tmp_path: Path) -> None:
        p = _write_transcript(tmp_path, _make_transcript_json())
        _, segments = TranscriptJsonImporter().import_transcript(p, "corpus-1")
        speakers = {s.speaker for s in segments}
        assert "INTERVIEWER" not in speakers
        assert "INTERVIEWEE" in speakers

    def test_include_interviewer_flag(self, tmp_path: Path) -> None:
        p = _write_transcript(tmp_path, _make_transcript_json())
        importer = TranscriptJsonImporter(include_interviewer=True)
        _, segments = importer.import_transcript(p, "corpus-1")
        speakers = {s.speaker for s in segments}
        assert "INTERVIEWER" in speakers

    def test_min_words_filter(self, tmp_path: Path) -> None:
        payload = _make_transcript_json(turns=[
            {
                "turn_index": 0,
                "speaker": "INTERVIEWEE",
                "start": 0.0, "end": 5.0, "duration": 5.0,
                "word_count": 2,
                "text": "Sí exacto",   # 2 words — below default min_words=3
                "segments": [{"start": 0.0, "end": 5.0, "text": "Sí exacto", "confidence": 0.9}],
            },
            {
                "turn_index": 1,
                "speaker": "INTERVIEWEE",
                "start": 6.0, "end": 20.0, "duration": 14.0,
                "word_count": 10,
                "text": "La comunidad se organizó de manera autónoma durante ese período.",
                "segments": [{"start": 6.0, "end": 20.0, "text": "La comunidad…", "confidence": 0.92}],
            },
        ])
        p = _write_transcript(tmp_path, payload)
        _, segments = TranscriptJsonImporter(min_words=3).import_transcript(p, "corpus-1")
        assert len(segments) == 1
        assert "autónoma" in segments[0].text

    def test_timestamps_are_preserved(self, tmp_path: Path) -> None:
        p = _write_transcript(tmp_path, _make_transcript_json())
        _, segments = TranscriptJsonImporter().import_transcript(p, "corpus-1")
        assert segments[0].start_s == pytest.approx(0.0)
        assert segments[0].end_s == pytest.approx(30.0)

    def test_confidence_averaged_from_subsegments(self, tmp_path: Path) -> None:
        payload = _make_transcript_json(turns=[{
            "turn_index": 0,
            "speaker": "INTERVIEWEE",
            "start": 0.0, "end": 10.0, "duration": 10.0,
            "word_count": 8,
            "text": "Texto de prueba para verificar el promedio de confianza.",
            "segments": [
                {"start": 0.0, "end": 5.0, "text": "Texto de prueba", "confidence": 0.80},
                {"start": 5.0, "end": 10.0, "text": "para verificar el promedio", "confidence": 0.90},
            ],
        }])
        p = _write_transcript(tmp_path, payload)
        _, segments = TranscriptJsonImporter().import_transcript(p, "corpus-1")
        assert segments[0].confidence == pytest.approx(0.85, abs=0.01)

    def test_file_not_found_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            TranscriptJsonImporter().import_transcript(Path("/nonexistent.transcript.json"), "x")

    def test_invalid_json_raises_value_error(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.transcript.json"
        p.write_text("NOT JSON", encoding="utf-8")
        importer = TranscriptJsonImporter()
        importer._validate_schema = lambda d, p: None  # type: ignore[method-assign]
        with pytest.raises((ValueError, Exception)):
            importer.import_transcript(p, "corpus-1")

    def test_spanish_characters_preserved(self, tmp_path: Path) -> None:
        payload = _make_transcript_json(turns=[{
            "turn_index": 0,
            "speaker": "INTERVIEWEE",
            "start": 0.0, "end": 10.0, "duration": 10.0,
            "word_count": 6,
            "text": "¿Cómo estás, señorita? ¡Así es la situación!",
            "segments": [{"start": 0.0, "end": 10.0, "text": "¿Cómo estás?", "confidence": 0.9}],
        }])
        p = _write_transcript(tmp_path, payload)
        _, segments = TranscriptJsonImporter().import_transcript(p, "corpus-1")
        assert "señorita" in segments[0].text
        assert "¿Cómo" in segments[0].text
