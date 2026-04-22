"""
ollama_adapter.py — Ollama adapter (Tier 1 — interactive local inference)
=========================================================================

Use Ollama for interactive tasks where latency matters:
  - Per-segment code suggestions during reading/coding sessions
  - Quick duplicate-code warnings
  - Candidate similar excerpts (before vector retrieval)

Recommended models on your university server hardware
------------------------------------------------------
  mistral:7b       — 4 GB RAM, ~5–15 s/call     — default, best balance
  phi3:mini        — 2 GB RAM, ~3–8 s/call      — fastest
  mixtral:8x7b     — 26 GB RAM, ~30–60 s/call   — best quality (server only)

Dependencies
------------
    pip install ollama
    # Separately: install Ollama from https://ollama.com
    # Then: ollama pull mistral:7b
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from tenacity import retry, stop_after_attempt, wait_fixed

from thematic.domain.entities import ModelRun, ModelTier, utcnow
from thematic.infrastructure.llm import prompt_library as P

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "mistral:7b"
_DEFAULT_HOST = "http://localhost:11434"
_TEMPERATURE = 0.3
_MAX_TOKENS = 2048


class OllamaLLMAdapter:
    """
    LLM adapter backed by a locally running Ollama server.

    Satisfies the ``LLMService`` protocol.

    Parameters
    ----------
    model:
        Ollama model tag, e.g. ``"mistral:7b"`` or ``"phi3:mini"``.
    host:
        Ollama server URL.  Default: ``http://localhost:11434``.
    project_id:
        Used for ``ModelRun`` records.

    Example
    -------
    >>> adapter = OllamaLLMAdapter(model="mistral:7b")
    >>> result = adapter.suggest_codes(
    ...     segment_text="Me quitaron el espacio de trabajo sin consultarnos...",
    ...     existing_codes=["loss_of_autonomy"],
    ...     codebook_context="Community pedagogical practices",
    ...     project_id="proj-abc",
    ... )
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        host: str = _DEFAULT_HOST,
        project_id: str = "",
    ) -> None:
        self._model = model
        self._host = host
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
    ) -> list[dict[str, Any]]:
        system = P.suggest_codes_system()
        user = P.suggest_codes_user(segment_text, existing_codes, codebook_context)
        raw = self._call(system, user, task="suggest_codes", project_id=project_id)
        return self._parse_list(raw)

    def find_similar_excerpts(
        self,
        reference_text: str,
        candidate_texts: list[str],
    ) -> list[dict[str, Any]]:
        system = P.find_similar_excerpts_system()
        user = P.find_similar_excerpts_user(reference_text, candidate_texts)
        raw = self._call(system, user, task="find_similar_excerpts")
        return self._parse_list(raw)

    def propose_cluster_label(
        self,
        excerpts: list[str],
        existing_categories: list[str],
    ) -> dict[str, Any]:
        system = P.propose_cluster_label_system()
        user = P.propose_cluster_label_user(excerpts, existing_categories)
        raw = self._call(system, user, task="propose_cluster_label")
        return self._parse_dict(raw)

    def synthesize_theme(
        self,
        category_labels: list[str],
        supporting_excerpts: list[str],
        project_context: str,
    ) -> dict[str, Any]:
        system = P.synthesize_theme_system()
        user = P.synthesize_theme_user(category_labels, supporting_excerpts, project_context)
        raw = self._call(system, user, task="synthesize_theme")
        return self._parse_dict(raw)

    def surface_contradictions(
        self,
        excerpts_by_source: dict[str, list[str]],
        research_question: str,
    ) -> list[dict[str, Any]]:
        system = P.surface_contradictions_system()
        user = P.surface_contradictions_user(excerpts_by_source, research_question)
        raw = self._call(system, user, task="surface_contradictions")
        return self._parse_list(raw)

    def list_available_models(self) -> list[str]:
        """Return model tags available on the local Ollama server."""
        client = self._ensure_client()
        try:
            models = client.list()
            return [m.model for m in models.models]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list Ollama models: %s", exc)
            return []

    def is_available(self) -> bool:
        """Return True if the Ollama server is reachable."""
        try:
            self._ensure_client()
            self.list_available_models()
            return True
        except Exception:  # noqa: BLE001
            return False

    # ── private ───────────────────────────────────────────────────────────────

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import ollama  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "ollama package is required for Tier 1 local inference.\n"
                "Install: pip install ollama\n"
                "Then install Ollama: https://ollama.com\n"
                "Then pull a model: ollama pull mistral:7b"
            ) from exc
        self._client = ollama.Client(host=self._host)
        return self._client

    @retry(stop=stop_after_attempt(2), wait=wait_fixed(1), reraise=True)
    def _call(
        self,
        system: str,
        user: str,
        task: str,
        project_id: str = "",
    ) -> str:
        """Make one Ollama inference call and return the raw text response."""
        client = self._ensure_client()
        pid = project_id or self._project_id

        prompt_hash = hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()
        logger.info("Ollama call: task='%s', model='%s'", task, self._model)

        response = client.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            options={"temperature": _TEMPERATURE, "num_predict": _MAX_TOKENS},
        )

        run = ModelRun.create(
            project_id=pid,
            model_name=self._model,
            model_tier=ModelTier.LOCAL_FAST,
            task=task,
            prompt_hash=prompt_hash,
            temperature=_TEMPERATURE,
            library_version=P.PROMPT_LIBRARY_VERSION,
        )
        logger.debug("ModelRun: %s", run.id)

        text = response.message.content if response.message else ""
        logger.debug("Ollama response (%d chars): %s…", len(text), text[:80])
        return text

    @staticmethod
    def _clean_json(text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        return text.strip()

    def _parse_list(self, text: str) -> list[dict[str, Any]]:
        try:
            result = json.loads(self._clean_json(text))
            return result if isinstance(result, list) else []
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error (Ollama): %s\nRaw: %s", exc, text[:200])
            return []

    def _parse_dict(self, text: str) -> dict[str, Any]:
        try:
            result = json.loads(self._clean_json(text))
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError as exc:
            logger.error("JSON parse error (Ollama): %s\nRaw: %s", exc, text[:200])
            return {}
