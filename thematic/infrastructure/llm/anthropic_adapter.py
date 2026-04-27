"""
anthropic_adapter.py — Claude API adapter (Tier 2 — synthesis & long-context)
==============================================================================

Use Claude for tasks that benefit from large context windows and high-quality
reasoning across many excerpts:
  - Theme synthesis across an entire corpus
  - Contradiction surfacing across multiple interviews
  - Cluster label proposals for large clusters

Do NOT use Claude for interactive per-segment coding (too slow, costs money).
Use Ollama (Tier 1) for that instead.

Privacy note
------------
Interview text leaves the local machine when this adapter is called.  For
research with privacy-sensitive participants, anonymize participant names in
segments before calling any method here.  The ``mask_speakers`` option on
``TranscriptJsonImporter`` can help.

Dependencies
------------
    pip install anthropic
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential

from thematic.domain.entities import ModelRun, ModelTier, new_id, utcnow
from thematic.infrastructure.llm import prompt_library as P

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 4096
_TEMPERATURE = 0.3   # Low temperature for analytical consistency


class AnthropicLLMAdapter:
    """
    LLM adapter backed by the Anthropic Claude API.

    Satisfies the ``LLMService`` protocol.

    Parameters
    ----------
    api_key:
        Anthropic API key.  Defaults to the ``ANTHROPIC_API_KEY`` environment
        variable.  Never hard-code this value.
    model:
        Model identifier.  Defaults to Claude Sonnet 4.6 — a strong balance
        of speed, quality, and cost for research synthesis tasks.
    project_id:
        Used for ``ModelRun`` records.  Pass the active project ID.

    Example
    -------
    >>> adapter = AnthropicLLMAdapter()
    >>> suggestions = adapter.suggest_codes(
    ...     segment_text="Me echaron del parque sin ninguna razón...",
    ...     existing_codes=["exclusion_from_spaces", "discrimination"],
    ...     codebook_context="Pedagogical practices in urban community spaces",
    ...     project_id="proj-123",
    ... )
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        project_id: str = "",
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._model = model
        self._project_id = project_id
        self._client = None  # lazy init

    # ── protocol property ────────────────────────────────────────────────────

    @property
    def model_name(self) -> str:
        return self._model

    # ── public API ────────────────────────────────────────────────────────────

    def suggest_codes(
        self,
        segment_text: str,
        existing_codes: list[str],
        codebook_context: str,
        project_id: str,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Suggest qualitative codes for one segment."""
        system = P.suggest_codes_system()
        user = P.suggest_codes_user(segment_text, existing_codes, codebook_context, language=language)
        raw = self._call(system, user, task="suggest_codes", project_id=project_id)
        return self._parse_list(raw)

    def find_similar_excerpts(
        self,
        reference_text: str,
        candidate_texts: list[str],
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Assess thematic similarity between a reference and candidates."""
        system = P.find_similar_excerpts_system()
        user = P.find_similar_excerpts_user(reference_text, candidate_texts, language=language)
        raw = self._call(system, user, task="find_similar_excerpts")
        return self._parse_list(raw)

    def propose_cluster_label(
        self,
        excerpts: list[str],
        existing_categories: list[str],
        language: str = "en",
    ) -> dict[str, Any]:
        """Propose a category label for a cluster of excerpts."""
        system = P.propose_cluster_label_system()
        user = P.propose_cluster_label_user(excerpts, existing_categories, language=language)
        raw = self._call(system, user, task="propose_cluster_label")
        return self._parse_dict(raw)

    def synthesize_theme(
        self,
        category_labels: list[str],
        supporting_excerpts: list[str],
        project_context: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Draft a theme narrative from categories and evidence."""
        system = P.synthesize_theme_system()
        user = P.synthesize_theme_user(category_labels, supporting_excerpts, project_context, language=language)
        raw = self._call(system, user, task="synthesize_theme")
        return self._parse_dict(raw)

    def surface_contradictions(
        self,
        excerpts_by_source: dict[str, list[str]],
        research_question: str,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Identify divergences across sources."""
        system = P.surface_contradictions_system()
        user = P.surface_contradictions_user(excerpts_by_source, research_question, language=language)
        raw = self._call(system, user, task="surface_contradictions")
        return self._parse_list(raw)

    # ── private ───────────────────────────────────────────────────────────────

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for Tier 2 analysis.\n"
                "Install: pip install anthropic"
            ) from exc
        if not self._api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Set it in .env or export it as an environment variable."
            )
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call(
        self,
        system: str,
        user: str,
        task: str,
        project_id: str = "",
    ) -> str:
        """Make one API call and return the raw text response."""
        client = self._ensure_client()
        pid = project_id or self._project_id

        prompt_hash = hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()

        logger.info("Claude API call: task='%s', model='%s'", task, self._model)

        message = client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        # Log the model run for reproducibility.
        run = ModelRun.create(
            project_id=pid,
            model_name=self._model,
            model_tier=ModelTier.CLOUD,
            task=task,
            prompt_hash=prompt_hash,
            temperature=_TEMPERATURE,
            max_tokens=_MAX_TOKENS,
            library_version=P.PROMPT_LIBRARY_VERSION,
        )
        logger.debug("ModelRun created: %s", run.id)

        response_text = message.content[0].text if message.content else ""
        logger.debug("Claude response (%d chars): %s…", len(response_text), response_text[:80])
        return response_text

    @staticmethod
    def _clean_json(text: str) -> str:
        """Strip markdown fences and whitespace from a JSON response."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return text.strip()

    def _parse_list(self, text: str) -> list[dict[str, Any]]:
        try:
            result = json.loads(self._clean_json(text))
            if isinstance(result, list):
                return result
            logger.warning("Expected JSON array, got %s — wrapping.", type(result))
            return [result] if isinstance(result, dict) else []
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in Claude response: %s\nRaw: %s", exc, text[:200])
            return []

    def _parse_dict(self, text: str) -> dict[str, Any]:
        try:
            result = json.loads(self._clean_json(text))
            if isinstance(result, dict):
                return result
            logger.warning("Expected JSON object, got %s.", type(result))
            return {}
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error in Claude response: %s\nRaw: %s", exc, text[:200])
            return {}