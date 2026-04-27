"""
coding.py — Coding workflow use cases
======================================

Application layer: orchestrates the core analytical workflow of open coding,
AI-assisted suggestions, and codebook management.

CRITICAL: AI suggestions are never silently adopted.  Every ``AISuggestion``
starts with status=PENDING and requires explicit analyst action (accept/revise/reject).

Use cases
---------
ApplyCodeUseCase          — analyst manually applies a code to a segment
SuggestCodesUseCase       — get AI suggestions for a segment
AcceptSuggestionUseCase   — analyst accepts a pending AI suggestion
RejectSuggestionUseCase   — analyst rejects a pending AI suggestion
CreateCodeUseCase         — add a new code to the codebook
FindSimilarSegmentsUseCase — retrieve semantically similar segments
"""

from __future__ import annotations

import logging
from pathlib import Path

from thematic.domain.entities import (
    AISuggestion,
    AISuggestionStatus,
    Code,
    CodingDecision,
    ModelRun,
    ModelTier,
    new_id,
)
from thematic.domain.protocols import (
    AISuggestionRepository,
    CodeRepository,
    CodingDecisionRepository,
    EmbeddingService,
    LLMService,
    ModelRunRepository,
    SegmentRepository,
)

logger = logging.getLogger(__name__)


class CreateCodeUseCase:
    """
    Add a new code to the project codebook.

    Parameters
    ----------
    code_repo: Persists the new code.
    """

    def __init__(self, code_repo: CodeRepository) -> None:
        self._code_repo = code_repo

    def execute(
        self,
        project_id: str,
        label: str,
        definition: str,
        inclusion_criteria: str = "",
        exclusion_criteria: str = "",
    ) -> Code:
        """
        Create and persist a new code.

        Parameters
        ----------
        project_id:           Parent project.
        label:                Short label (snake_case recommended).
        definition:           Full definition the analyst will apply.
        inclusion_criteria:   What must be present to apply this code.
        exclusion_criteria:   What disqualifies a segment.

        Returns
        -------
        Code
            The created code entity.

        Raises
        ------
        ValueError
            If a code with the same label already exists in this project.
        """
        existing = self._code_repo.get_by_label(project_id, label)
        if existing is not None:
            raise ValueError(
                f"Code '{label}' already exists in project '{project_id}'. "
                "Use a distinct label or update the existing code."
            )

        code = Code(
            id=new_id(),
            project_id=project_id,
            label=label,
            definition=definition,
            inclusion_criteria=inclusion_criteria,
            exclusion_criteria=exclusion_criteria,
        )
        self._code_repo.save(code)
        logger.info("Code created: '%s' in project '%s'.", label, project_id)
        return code


class ApplyCodeUseCase:
    """
    Analyst manually applies a code to a segment.

    Parameters
    ----------
    decision_repo: Persists the coding decision.
    code_repo:     Validates the code exists.
    segment_repo:  Validates the segment exists.
    """

    def __init__(
        self,
        decision_repo: CodingDecisionRepository,
        code_repo: CodeRepository,
        segment_repo: SegmentRepository,
    ) -> None:
        self._decision_repo = decision_repo
        self._code_repo = code_repo
        self._segment_repo = segment_repo

    def execute(
        self,
        segment_id: str,
        code_id: str,
        analyst: str,
        note: str = "",
    ) -> CodingDecision:
        """
        Apply *code_id* to *segment_id* by *analyst*.

        Parameters
        ----------
        segment_id: The segment to code.
        code_id:    The code to apply.
        analyst:    Analyst identifier (name or email).
        note:       Optional rationale for this specific application.

        Returns
        -------
        CodingDecision
            The created decision entity.

        Raises
        ------
        ValueError
            If the segment or code do not exist.
        """
        if self._segment_repo.get(segment_id) is None:
            raise ValueError(f"Segment '{segment_id}' not found.")
        if self._code_repo.get(code_id) is None:
            raise ValueError(f"Code '{code_id}' not found.")

        decision = CodingDecision.create(
            segment_id=segment_id,
            code_id=code_id,
            analyst=analyst,
            note=note,
            is_ai=False,
        )
        self._decision_repo.save(decision)
        logger.debug("Code applied: segment=%s code=%s analyst=%s", segment_id, code_id, analyst)
        return decision


class SuggestCodesUseCase:
    """
    Request AI code suggestions for one segment.

    The suggestions are persisted as ``AISuggestion`` entities with
    status=PENDING.  They do NOT become coding decisions until an analyst
    explicitly accepts them via ``AcceptSuggestionUseCase``.

    Parameters
    ----------
    llm_service:        The LLM adapter (Ollama or Claude).
    code_repo:          Provides existing codebook labels for context.
    segment_repo:       Fetches the segment text.
    suggestion_repo:    Persists the suggestions.
    run_repo:           Persists the ModelRun for audit.
    """

    def __init__(
        self,
        llm_service: LLMService,
        code_repo: CodeRepository,
        segment_repo: SegmentRepository,
        suggestion_repo: AISuggestionRepository,
        run_repo: ModelRunRepository,
    ) -> None:
        self._llm = llm_service
        self._code_repo = code_repo
        self._segment_repo = segment_repo
        self._suggestion_repo = suggestion_repo
        self._run_repo = run_repo

    def execute(
        self,
        segment_id: str,
        project_id: str,
        codebook_context: str,
    ) -> list[AISuggestion]:
        """
        Generate and persist AI suggestions for *segment_id*.

        Parameters
        ----------
        segment_id:        The segment to get suggestions for.
        project_id:        Parent project (used to fetch the codebook).
        codebook_context:  Research question or focus passed to the model.

        Returns
        -------
        list[AISuggestion]
            Pending suggestions — never already-accepted decisions.

        Raises
        ------
        ValueError
            If the segment is not found.
        """
        segment = self._segment_repo.get(segment_id)
        if segment is None:
            raise ValueError(f"Segment '{segment_id}' not found.")

        existing_codes = [c.label for c in self._code_repo.list_for_project(project_id)]

        logger.info(
            "Requesting suggestions: segment='%s', model='%s'",
            segment_id, self._llm.model_name,
        )

        raw_suggestions = self._llm.suggest_codes(
            segment_text=segment.text,
            existing_codes=existing_codes,
            codebook_context=codebook_context,
            project_id=project_id,
        )

        # Build a ModelRun record.
        run = ModelRun.create(
            project_id=project_id,
            model_name=self._llm.model_name,
            model_tier=ModelTier.LOCAL_FAST,
            task="suggest_codes",
            prompt_hash="",   # adapter sets this internally
        )
        self._run_repo.save(run)

        suggestions = [
            AISuggestion.create(
                run_id=run.id,
                segment_id=segment_id,
                suggested_code_label=s.get("label", "unlabelled"),
                justification=s.get("justification", ""),
                confidence=float(s.get("confidence", 0.0)),
            )
            for s in raw_suggestions
            if isinstance(s, dict)
        ]

        self._suggestion_repo.save_batch(suggestions)
        logger.info("Created %d suggestion(s) for segment '%s'.", len(suggestions), segment_id)
        return suggestions


class AcceptSuggestionUseCase:
    """
    Analyst accepts a pending AI suggestion, creating a real coding decision.

    Parameters
    ----------
    suggestion_repo: Updates suggestion status.
    decision_repo:   Persists the new coding decision.
    code_repo:       Looks up or creates the suggested code.
    """

    def __init__(
        self,
        suggestion_repo: AISuggestionRepository,
        decision_repo: CodingDecisionRepository,
        code_repo: CodeRepository,
    ) -> None:
        self._suggestion_repo = suggestion_repo
        self._decision_repo = decision_repo
        self._code_repo = code_repo

    def execute(
        self,
        suggestion_id: str,
        analyst: str,
        note: str = "",
        *,
        create_code_if_missing: bool = True,
        project_id: str = "",
    ) -> CodingDecision:
        """
        Accept *suggestion_id*, creating a ``CodingDecision``.

        Parameters
        ----------
        suggestion_id:          The suggestion to accept.
        analyst:                Analyst who reviewed and accepted it.
        note:                   Optional annotation added during review.
        create_code_if_missing: If the suggested label is new, create the
                                code automatically (True by default).
        project_id:             Required when create_code_if_missing=True.

        Returns
        -------
        CodingDecision
            The new decision with ``is_ai=True``.
        """
        # Load the suggestion from the repo
        suggestion = self._suggestion_repo.get(suggestion_id)
        if suggestion is None:
            raise ValueError(f"Suggestion '{suggestion_id}' not found.")

        if suggestion.status != AISuggestionStatus.PENDING:
            raise ValueError(
                f"Suggestion '{suggestion_id}' is already {suggestion.status.value} "
                "and cannot be accepted again."
            )

        label = note.strip() if note.strip() else suggestion.suggested_code_label

        # Find or create the code
        code = self._code_repo.get_by_label(project_id, label)
        if code is None:
            if not create_code_if_missing:
                raise ValueError(
                    f"Code '{label}' not found in project '{project_id}'. "
                    "Pass create_code_if_missing=True to create it automatically."
                )
            if not project_id:
                raise ValueError("project_id is required when create_code_if_missing=True.")
            code = CreateCodeUseCase(self._code_repo).execute(
                project_id=project_id,
                label=label,
                definition=f"AI suggested: {suggestion.justification}",
            )

        # Create the coding decision flagged as AI-originated
        decision = CodingDecision(
            id=new_id(),
            segment_id=suggestion.segment_id,
            code_id=code.id,
            analyst=analyst,
            note=note,
            is_ai=True,
            ai_run_id=suggestion.run_id,
        )
        self._decision_repo.save(decision)

        # Mark suggestion as accepted so the audit trail is correct
        self._suggestion_repo.update_status(suggestion_id, AISuggestionStatus.ACCEPTED.value)

        return decision


class FindSimilarSegmentsUseCase:
    """
    Retrieve semantically similar segments using vector search.

    Useful during coding to find passages that may share the same code,
    reducing analyst effort and improving coding consistency.

    Parameters
    ----------
    embedding_service: Provides vector search.
    segment_repo:      Fetches segment text for display.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        segment_repo: SegmentRepository,
    ) -> None:
        self._embedder = embedding_service
        self._segment_repo = segment_repo

    def execute(
        self,
        query_text: str,
        top_k: int = 10,
        project_id: str | None = None,
    ) -> list[dict[str, object]]:
        """
        Find segments semantically similar to *query_text*.

        Parameters
        ----------
        query_text:  The reference text (usually a segment being coded).
        top_k:       Number of results to return.
        project_id:  Restrict results to this project.

        Returns
        -------
        list[dict]
            Each dict: {segment_id, text, speaker, score}.
        """
        hits = self._embedder.find_similar(query_text, top_k=top_k, project_id=project_id)
        results = []
        for segment_id, score in hits:
            seg = self._segment_repo.get(segment_id)
            if seg is None:
                continue
            results.append({
                "segment_id": segment_id,
                "text": seg.text,
                "speaker": seg.speaker,
                "start_s": seg.start_s,
                "score": round(score, 4),
            })
        return results