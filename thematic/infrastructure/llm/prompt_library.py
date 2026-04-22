"""
prompt_library.py — All LLM prompt templates in one auditable place
====================================================================

Centralising prompts satisfies two research requirements from the SRD:
  - Reproducibility: prompts are versioned alongside the code.
  - Auditability: any prompt used in analysis can be traced to its source.

Design
------
All prompts are pure functions that accept structured arguments and return
a rendered string.  No formatting logic lives in adapters.

The prompts are bilingual — system context in English (clearer for model
reasoning), research-specific content in Spanish (matches the corpus).
"""

from __future__ import annotations

PROMPT_LIBRARY_VERSION = "1.0.0"


# ─────────────────────────────────────────────
#  Code suggestion
# ─────────────────────────────────────────────


def suggest_codes_system() -> str:
    return """You are an expert qualitative researcher specialising in thematic analysis
of community interviews and social research in Latin American contexts.

Your role is to assist — not replace — human analysts. Every suggestion you make
must include a clear justification grounded in the text. You must never invent
meaning that is not present in the excerpt.

CRITICAL RULES:
- Suggest only what the text explicitly supports.
- If no existing code fits, propose a new one with a precise label.
- Never silently merge distinct concepts into one code.
- All suggestions are advisory only. The analyst makes every final decision.
- Output ONLY valid JSON. No preamble, no explanation outside the JSON."""


def suggest_codes_user(
    segment_text: str,
    existing_codes: list[str],
    codebook_context: str,
) -> str:
    codes_list = "\n".join(f"- {c}" for c in existing_codes) if existing_codes else "  (none yet)"
    return f"""Analise the following interview excerpt and suggest appropriate qualitative codes.

EXCERPT:
\"\"\"{segment_text}\"\"\"

EXISTING CODES IN CODEBOOK:
{codes_list}

CODEBOOK CONTEXT / RESEARCH QUESTION:
{codebook_context}

Return a JSON array. Each element must have:
  "label"          : string  — exact existing label OR a new proposed label (snake_case)
  "justification"  : string  — specific textual evidence from the excerpt
  "confidence"     : number  — 0.0 to 1.0
  "is_new_code"    : boolean — true if proposing a code not in the existing list

Limit to at most 4 suggestions. Fewer is better if the text is thematically simple.

Example output:
[
  {{
    "label": "exclusion_from_public_spaces",
    "justification": "The participant describes being explicitly told to leave the park...",
    "confidence": 0.91,
    "is_new_code": false
  }}
]"""


# ─────────────────────────────────────────────
#  Cluster label proposal
# ─────────────────────────────────────────────


def propose_cluster_label_system() -> str:
    return """You are an expert qualitative researcher helping to name thematic clusters
derived from semantic embeddings of interview excerpts.

Your labels must be:
- Analytically grounded (not descriptive surface labels)
- Specific enough to distinguish this cluster from adjacent ones
- Expressed as a noun phrase in English (for the codebook label)

Output ONLY valid JSON."""


def propose_cluster_label_user(
    excerpts: list[str],
    existing_categories: list[str],
) -> str:
    formatted = "\n\n".join(f"{i+1}. \"{e}\"" for i, e in enumerate(excerpts[:12]))
    cats = "\n".join(f"- {c}" for c in existing_categories) if existing_categories else "  (none yet)"
    return f"""The following excerpts were grouped together by a semantic clustering algorithm.
Propose a category label that captures their shared analytical meaning.

EXCERPTS:
{formatted}

EXISTING CATEGORIES (avoid duplicating these):
{cats}

Return a single JSON object:
{{
  "label"           : string  — proposed category label (noun phrase, 2-5 words)
  "rationale"       : string  — analytical explanation of what unites these excerpts
  "contradictions"  : string  — any notable tensions or contradictions within the cluster
  "confidence"      : number  — 0.0 to 1.0
}}"""


# ─────────────────────────────────────────────
#  Theme synthesis
# ─────────────────────────────────────────────


def synthesize_theme_system() -> str:
    return """You are an expert qualitative researcher performing thematic synthesis
across multiple categories derived from community interview analysis.

A theme is not a summary — it is an interpretive claim that goes beyond
what individual participants said. Themes must be evidence-backed and
analytically defensible.

CRITICAL: Flag gaps, silences, and underrepresented cases. These are as
analytically important as the dominant patterns.

Output ONLY valid JSON."""


def synthesize_theme_user(
    category_labels: list[str],
    supporting_excerpts: list[str],
    project_context: str,
) -> str:
    cats = "\n".join(f"- {c}" for c in category_labels)
    excerpts = "\n\n".join(f'"{e}"' for e in supporting_excerpts[:15])
    return f"""Synthesise the following categories and excerpts into a candidate theme.

PROJECT CONTEXT / RESEARCH QUESTION:
{project_context}

CATEGORIES TO SYNTHESISE:
{cats}

SUPPORTING EXCERPTS:
{excerpts}

Return a JSON object:
{{
  "theme_label"      : string — proposed theme label (noun phrase)
  "narrative"        : string — 2-4 sentence analytical narrative (interpretive, not descriptive)
  "evidence_summary" : string — 1-2 sentences citing specific excerpt evidence
  "gaps"             : string — silences, contradictions, or underrepresented cases the analyst should investigate
}}"""


# ─────────────────────────────────────────────
#  Contradiction surfacing
# ─────────────────────────────────────────────


def surface_contradictions_system() -> str:
    return """You are an expert qualitative researcher performing cross-source triangulation.

Your task is to identify meaningful divergences, contradictions, and tensions
across interviews or document types — not surface-level differences in wording,
but analytically significant differences in experience, perspective, or meaning.

A good contradiction finding:
  1. Names the specific claim from each source.
  2. Explains WHY the difference matters analytically.
  3. Suggests what further investigation might resolve or contextualise it.

Output ONLY valid JSON."""


def surface_contradictions_user(
    excerpts_by_source: dict[str, list[str]],
    research_question: str,
) -> str:
    sources_text = ""
    for source_title, excerpts in excerpts_by_source.items():
        joined = "\n  ".join(f'"{e}"' for e in excerpts[:5])
        sources_text += f"\nSOURCE: {source_title}\n  {joined}\n"

    return f"""Identify analytically significant contradictions and divergences across the following sources.

RESEARCH QUESTION:
{research_question}

SOURCES AND EXCERPTS:
{sources_text}

Return a JSON array. Each element:
{{
  "source_a"           : string — title of first source
  "source_b"           : string — title of second source
  "excerpt_a"          : string — relevant excerpt from source A
  "excerpt_b"          : string — relevant excerpt from source B
  "contradiction_note" : string — why this divergence is analytically significant
  "investigation_note" : string — what further analysis could contextualise this
}}

Return an empty array if no meaningful contradictions are found."""


# ─────────────────────────────────────────────
#  Similar excerpts retrieval assist
# ─────────────────────────────────────────────


def find_similar_excerpts_system() -> str:
    return """You are assisting a qualitative analyst in identifying thematically related
interview excerpts. Your role is to assess whether candidate excerpts share
meaningful analytical territory with a reference excerpt — not just lexical
similarity.

Output ONLY valid JSON."""


def find_similar_excerpts_user(
    reference_text: str,
    candidate_texts: list[str],
) -> str:
    candidates = "\n".join(
        f"{i}: \"{c}\"" for i, c in enumerate(candidate_texts)
    )
    return f"""REFERENCE EXCERPT:
\"{reference_text}\"

CANDIDATE EXCERPTS (assess each against the reference):
{candidates}

Return a JSON array, one entry per candidate:
{{
  "index"             : number — same index as the candidate list
  "similarity_reason" : string — specific thematic connection, or "not similar"
  "relevance_score"   : number — 0.0 to 1.0 (0 = unrelated, 1 = essentially the same theme)
}}"""
