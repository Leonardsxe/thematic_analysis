"""
transcript_importer.py — Import .transcript.json from the audio-transcriber project
====================================================================================

This is the explicit import contract between the two projects.

The audio-transcriber produces ``.transcript.json`` files with this schema
(schema_version 1.0):

.. code-block:: json

    {
      "schema_version": "1.0",
      "metadata": {
        "source": "/abs/path/to/interview.mp3",
        "duration_s": 2847.3,
        "language": "es",
        "avg_confidence": 0.91
      },
      "speakers": {
        "INTERVIEWER": {"total_speech_s": 342.1, "turn_count": 47, "word_count": 1820},
        "INTERVIEWEE": {"total_speech_s": 2505.2, "turn_count": 44, "word_count": 18340}
      },
      "turns": [
        {
          "turn_index": 0,
          "speaker": "INTERVIEWEE",
          "start": 0.0,
          "end": 12.4,
          "duration": 12.4,
          "word_count": 23,
          "text": "Buenos días...",
          "segments": [{"start": 0.0, "end": 5.1, "text": "...", "confidence": 0.94}]
        }
      ]
    }

SRP: this module only parses JSON into domain entities.  It does not write
to any database or vector store.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from thematic.domain.entities import Segment, SegmentType, Source, SourceType

logger = logging.getLogger(__name__)

_SUPPORTED_SCHEMA_VERSION = "1.0"
_MIN_SEGMENT_WORDS = 3     # skip very short utterances like "Mm-hmm"
_INTERVIEWEE_SPEAKER = "INTERVIEWEE"


class TranscriptJsonImporter:
    """
    Parse a ``.transcript.json`` file from the audio-transcriber project.

    Satisfies the ``TranscriptImporter`` protocol.

    Parameters
    ----------
    min_words:
        Segments with fewer words than this are skipped.  Helps remove
        filler utterances that add noise to retrieval and clustering.
    include_interviewer:
        When False (default for thematic analysis), only INTERVIEWEE turns
        are imported.  Set True to include both speakers.
    """

    def __init__(
        self,
        *,
        min_words: int = _MIN_SEGMENT_WORDS,
        include_interviewer: bool = False,
    ) -> None:
        self._min_words = min_words
        self._include_interviewer = include_interviewer

    # ── public ───────────────────────────────────────────────────────────────

    def can_import(self, path: Path) -> bool:
        """Return True for .transcript.json files with the known schema."""
        if not path.is_file():
            return False
        if not path.name.endswith(".transcript.json"):
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("schema_version") == _SUPPORTED_SCHEMA_VERSION
        except (json.JSONDecodeError, OSError):
            return False

    def import_transcript(
        self,
        path: Path,
        corpus_id: str,
    ) -> tuple[Source, list[Segment]]:
        """
        Parse *path* and return ``(Source, [Segment, …])``.

        The ``Source`` captures file-level metadata.
        Each ``Segment`` is one speaker turn (INTERVIEWEE or both speakers,
        depending on ``include_interviewer``).

        Parameters
        ----------
        path:
            Path to the ``.transcript.json`` file.
        corpus_id:
            The corpus this source belongs to.

        Returns
        -------
        tuple[Source, list[Segment]]
            Source entity and ordered list of Segment entities.

        Raises
        ------
        ValueError
            If the file is not a valid transcript JSON or schema version
            is unsupported.
        FileNotFoundError
            If *path* does not exist.
        """
        if not path.exists():
            raise FileNotFoundError(f"Transcript file not found: {path}")

        raw = self._load_json(path)
        self._validate_schema(raw, path)

        meta = raw.get("metadata", {})
        source = self._build_source(raw, meta, path, corpus_id)
        segments = self._build_segments(raw.get("turns", []), source.id)

        logger.info(
            "Imported '%s': %d turn(s) → %d segment(s) after filtering",
            path.name,
            len(raw.get("turns", [])),
            len(segments),
        )
        return source, segments

    # ── private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load_json(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in '{path}': {exc}") from exc

    @staticmethod
    def _validate_schema(data: dict, path: Path) -> None:
        version = data.get("schema_version")
        if version != _SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported schema_version '{version}' in '{path}'. "
                f"Expected '{_SUPPORTED_SCHEMA_VERSION}'."
            )

    def _build_source(
        self,
        raw: dict,
        meta: dict,
        path: Path,
        corpus_id: str,
    ) -> Source:
        """Construct the Source entity from file-level metadata."""
        original_audio = meta.get("source", str(path))
        title = Path(original_audio).stem if original_audio else path.stem

        speakers = raw.get("speakers", {})
        word_count = sum(s.get("word_count", 0) for s in speakers.values())

        return Source(
            id=Source.create(
                corpus_id=corpus_id,
                source_type=SourceType.TRANSCRIPT,
                title=title,
                original_path=original_audio,
            ).id,
            corpus_id=corpus_id,
            source_type=SourceType.TRANSCRIPT,
            title=title,
            original_path=original_audio,
            word_count=word_count,
            import_metadata={
                "schema_version": raw.get("schema_version", ""),
                "language": meta.get("language", ""),
                "duration_s": str(meta.get("duration_s", "")),
                "avg_confidence": str(meta.get("avg_confidence", "")),
                "transcript_file": str(path),
            },
        )

    def _build_segments(self, turns: list[dict], source_id: str) -> list[Segment]:
        """Convert raw turn dicts into Segment entities, applying filters."""
        segments: list[Segment] = []
        kept_index = 0

        for turn in turns:
            speaker: str = turn.get("speaker", "UNKNOWN")

            # Speaker filter
            if not self._include_interviewer and speaker != _INTERVIEWEE_SPEAKER:
                continue

            text: str = turn.get("text", "").strip()
            word_count = len(text.split())

            # Length filter
            if word_count < self._min_words:
                logger.debug("Skipping short segment (%d words): '%s…'", word_count, text[:40])
                continue

            # Confidence: average across sub-segments
            sub_segs = turn.get("segments", [])
            confidence = (
                sum(s.get("confidence", 0.0) for s in sub_segs) / len(sub_segs)
                if sub_segs
                else 0.0
            )

            seg = Segment.from_speaker_turn(
                source_id=source_id,
                index=kept_index,
                text=text,
                speaker=speaker,
                start_s=float(turn.get("start", 0.0)),
                end_s=float(turn.get("end", 0.0)),
                confidence=round(confidence, 4),
            )
            segments.append(seg)
            kept_index += 1

        return segments
