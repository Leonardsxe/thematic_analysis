# thematic-analysis

Computer-assisted qualitative thematic analysis for interviews and community documents.

Separate project that integrates with the [audio-transcriber](../audio-transcriber) through an explicit import contract: the `.transcript.json` files it produces.

---

## What it does

- Imports `.transcript.json` files from the audio-transcriber, preserving speaker labels, timestamps, and confidence scores
- Provides a reading-first immersion workspace before formal coding
- Supports manual open coding and AI-assisted code suggestions (never auto-adopted)
- Builds a versioned codebook with definitions, inclusion/exclusion criteria, and examples
- Runs semantic clustering (HDBSCAN) on embeddings to surface candidate categories
- Surfaces cross-source contradictions and coverage gaps
- Exports evidence matrices, codebooks, and full audit trails

---

## Architecture

Clean Architecture (Hexagonal variant):

```
thematic-analysis/
├── thematic/
│   ├── domain/
│   │   ├── entities.py            ← 14 domain entities (frozen dataclasses)
│   │   └── protocols.py           ← 11 Protocol interfaces (Repository, LLM, Importer, Exporter)
│   │
│   ├── application/
│   │   ├── ingest.py              ← IngestTranscriptUseCase, RebuildEmbeddingsUseCase
│   │   ├── coding.py              ← ApplyCode, SuggestCodes, FindSimilarSegments, CreateCode
│   │   ├── clustering.py          ← RunClusteringUseCase (HDBSCAN + LLM label proposals)
│   │   └── export.py              ← EvidenceMatrix, Codebook, AuditTrail export use cases
│   │
│   ├── infrastructure/
│   │   ├── db/
│   │   │   ├── models.py          ← SQLAlchemy ORM tables (12 tables, SQLite + PostgreSQL)
│   │   │   └── repositories.py    ← 10 repository implementations (ORM ↔ domain entity mapping)
│   │   ├── embeddings/
│   │   │   └── chroma_service.py  ← ChromaDB + sentence-transformers (multilingual, Spanish-first)
│   │   ├── llm/
│   │   │   ├── prompt_library.py  ← all LLM prompts, versioned and auditable (v1.0.0)
│   │   │   ├── anthropic_adapter.py ← Claude API (Tier 2 — synthesis, long-context)
│   │   │   └── ollama_adapter.py  ← Ollama (Tier 1 — interactive, local)
│   │   └── importers/
│   │       └── transcript_importer.py ← reads .transcript.json import contract
│   │
│   └── presentation/
│       ├── app.py                 ← Streamlit entry point + Composition Root (dependency wiring)
│       └── pages/
│           ├── 01_corpus.py       ← project management, transcript import with live preview
│           ├── 02_immersion.py    ← read-first workspace, memos, bookmarks
│           ├── 03_coding.py       ← segment browser, manual coding, AI suggestions (accept/reject)
│           ├── 04_codebook.py     ← code CRUD, categories, theme management
│           ├── 05_clusters.py     ← HDBSCAN cluster review, promote to category, theme synthesis
│           ├── 06_comparison.py   ← code frequency matrix, contradiction analysis, coverage gaps
│           └── 07_export.py       ← evidence matrix, codebook, audit trail downloads
│
├── tests/
│   ├── unit/
│   │   ├── test_domain.py         ← 25 tests: entities, importer, Spanish chars, error handling
│   │   └── test_use_cases.py      ← 19 tests: all use cases with injected mocks
│   └── integration/               ← requires real DB + model (marked, skipped by default)
│
├── scripts/
│   └── import_transcripts.py      ← batch import from audio-transcriber output folder
│
├── docs/
├── .env.example
├── pyproject.toml
└── README.md
```

---

## AI model tiers

| Tier | Tool | Use for | Hardware |
|---|---|---|---|
| 1 | Ollama + Mistral 7B | Interactive coding suggestions, per-segment | Any (4 GB RAM) |
| 2 | Claude API | Theme synthesis, long-context contradiction analysis | Cloud (no local GPU needed) |
| 3 | Ollama + Mixtral | Heavy batch analysis | University server (64+ GB RAM) |

---

## Quick start

```bash
# 1. Create and activate venv
python -m venv .venv && source .venv/bin/activate

# 2. Install
pip install -e ".[dev]"

# 3. Install Ollama + a model
# https://ollama.com
ollama pull mistral:7b

# 4. Configure
cp .env.example .env

# 5. Import transcripts from the audio-transcriber project
python scripts/import_transcripts.py ../audio-transcriber/output \
    --project "My project" --corpus "Phase 1"

# 6. Launch dashboard
streamlit run thematic/presentation/app.py
```

---

## Running tests

```bash
source .venv/bin/activate
pytest tests/unit/ -v         # 29 tests, no model, no network, < 2 s
pytest tests/ -v              # all tests
```

---

## Import contract with audio-transcriber

The audio-transcriber produces `.transcript.json` files (schema version 1.0).
This project reads them via `TranscriptJsonImporter`. The contract is:

- `schema_version` must be `"1.0"`
- `turns` array with `speaker`, `start`, `end`, `text`, `segments[].confidence`
- `metadata.language`, `metadata.duration_s`, `metadata.avg_confidence`

No other dependency exists between the two projects.
