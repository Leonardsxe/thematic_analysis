# Architecture Overview — Thematic Analysis Platform

> Version 0.1.0 · April 2026

---

## 1. Design philosophy

The platform is designed around three constraints that follow directly from
its research context:

**Methodological auditability.** Every code, suggestion, cluster label,
and theme must be traceable to a source segment, an analyst identity, a
timestamp, and — when AI was involved — a model name and prompt hash.
No output can be adopted silently.

**Privacy-first.** Interviews with community participants may contain
sensitive material. The architecture defaults to local-only execution
(SQLite + ChromaDB + Ollama) and treats the cloud API (Claude) as an
opt-in tier for anonymised synthesis passes, not a default.

**Analyst sovereignty.** AI assistance is advisory only. The system
never automatically promotes a suggestion, cluster label, or theme
draft to a final finding. Every decision requires an explicit human
action.

These three constraints shape every layer of the architecture.

---

## 2. Relationship to the audio-transcriber project

The thematic analysis platform is a **separate project** that communicates
with the audio-transcriber through a single, explicit import contract:
the `.transcript.json` file format (schema version 1.0).

```
audio-transcriber project          thematic-analysis project
─────────────────────────          ─────────────────────────
  Whisper + pyannote
        │
        ▼
  .transcript.json   ──────────►  TranscriptJsonImporter
  (schema 1.0)                           │
                                         ▼
                                    domain entities
                                  (Source, Segment, …)
```

The audio-transcriber knows nothing about the thematic analysis platform.
The thematic analysis platform knows only the JSON schema, not any
internal class of the transcriber. Changing the transcriber's internals
never breaks the analysis platform as long as the schema version is
preserved.

The `.transcript.json` contract carries: speaker labels (`INTERVIEWER` /
`INTERVIEWEE`), start/end timestamps in seconds, per-segment confidence
scores, source audio path, language, and total duration.

---

## 3. Clean Architecture layers

The codebase is divided into four concentric layers. The dependency rule
is strict: **outer layers may import inner layers; inner layers never
import outer layers.**

```
╔══════════════════════════════════════════════════════════════╗
║  PRESENTATION                                                ║
║  Streamlit dashboard (app.py + 7 pages)                      ║
║  Scripts (import_transcripts.py)                             ║
╠══════════════════════════════════════════════════════════════╣
║  APPLICATION                                                 ║
║  Use cases: IngestTranscript, ApplyCode, SuggestCodes,       ║
║  RunClustering, BuildEvidenceMatrix, …                       ║
╠══════════════════════════════════════════════════════════════╣
║  INFRASTRUCTURE                                              ║
║  SQLAlchemy DB  ·  ChromaDB embeddings  ·  Ollama / Claude   ║
║  TranscriptJsonImporter  ·  SqlRepositories                  ║
╠══════════════════════════════════════════════════════════════╣
║  DOMAIN                                                      ║
║  Entities (frozen dataclasses)  ·  Protocols (interfaces)    ║
║  Zero external dependencies                                  ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 4. Domain layer

### 4.1 Value objects

All domain entities are **frozen dataclasses** — immutable by definition
and enforced at runtime by `FrozenInstanceError`. They carry zero
external dependencies: no SQLAlchemy, no Streamlit, no model SDK imports.

#### Enumerations

| Enum | Values |
|---|---|
| `SourceType` | `TRANSCRIPT`, `DOCUMENT`, `FIELD_NOTE`, `MEMO` |
| `SegmentType` | `SPEAKER_TURN`, `PARAGRAPH`, `EXCERPT` |
| `CodeRelationType` | `PARENT_CHILD`, `CAUSAL`, `CONTEXTUAL`, `CONTRASTIVE`, `TEMPORAL` |
| `AISuggestionStatus` | `PENDING`, `ACCEPTED`, `REVISED`, `REJECTED` |
| `ModelTier` | `LOCAL_FAST`, `LOCAL_HEAVY`, `CLOUD` |

#### Entity hierarchy

```
Project
  └── Corpus  (named collection, filterable by territory / period / group)
        └── Source  (one .transcript.json or document)
              └── Segment  (one speaker turn or paragraph — atomic analysis unit)
                    ├── CodingDecision  (code applied to this segment)
                    ├── Memo            (analyst note attached to this segment)
                    └── AISuggestion    (pending model suggestion for this segment)

Code  ──────────────────────────────────────── Codebook hierarchy:
  └── Category  (cluster of related codes)       Code → Category → Theme
        └── Theme  (final interpretive claim)

Cluster    (HDBSCAN output — candidate category, pending analyst review)
ModelRun   (audit record for every LLM inference call)
CodeRelation (directed relationship between two codes)
EvidenceRow / EvidenceMatrix  (export value objects)
```

#### Entity reference

| Entity | Key fields | Notes |
|---|---|---|
| `Project` | `id`, `name`, `description`, `created_at` | Top-level container |
| `Corpus` | `id`, `project_id`, `name`, `filters` | Filterable collection of sources |
| `Participant` | `id`, `project_id`, `pseudonym`, `metadata` | Referenced in transcripts |
| `Source` | `id`, `corpus_id`, `source_type`, `title`, `original_path`, `word_count` | One file |
| `Segment` | `id`, `source_id`, `segment_type`, `index`, `text`, `speaker`, `start_s`, `end_s`, `confidence`, `embedding_id` | Atomic unit |
| `Code` | `id`, `project_id`, `label`, `definition`, `inclusion_criteria`, `exclusion_criteria`, `examples`, `counterexamples`, `version`, `is_deprecated` | Codebook entry |
| `Category` | `id`, `project_id`, `label`, `rationale`, `theme_id` | Code grouping |
| `Theme` | `id`, `project_id`, `label`, `narrative`, `evidence_summary`, `is_published` | Final claim |
| `CodeRelation` | `source_code_id`, `target_code_id`, `relation_type`, `note` | Axial coding link |
| `CodingDecision` | `segment_id`, `code_id`, `analyst`, `note`, `is_ai`, `ai_run_id` | Every code application |
| `Memo` | `project_id`, `author`, `text`, `entity_type`, `entity_id` | Free-form note |
| `ModelRun` | `project_id`, `model_name`, `model_tier`, `task`, `prompt_hash`, `parameters` | LLM audit record |
| `AISuggestion` | `run_id`, `segment_id`, `suggested_code_label`, `justification`, `confidence`, `status` | Always starts PENDING |
| `Cluster` | `project_id`, `run_id`, `label`, `segment_ids`, `coherence_score`, `is_reviewed` | HDBSCAN output |
| `EvidenceMatrix` | `project_id`, `rows` | Export value object |

### 4.2 Protocols (structural interfaces)

All protocols use `typing.Protocol` with `@runtime_checkable`. A class
satisfies a protocol simply by having the right methods — no inheritance
required. This allows infrastructure adapters to be replaced without
touching domain or application code.

#### Repository protocols (10 total)

| Protocol | Key methods |
|---|---|
| `ProjectRepository` | `save`, `get`, `list_all`, `delete` |
| `CorpusRepository` | `save`, `get`, `list_for_project` |
| `SourceRepository` | `save`, `get`, `list_for_corpus`, `count_for_project` |
| `SegmentRepository` | `save_batch`, `get`, `list_for_source`, `list_for_project`, `update_embedding_id`, `count_for_project` |
| `CodeRepository` | `save`, `get`, `get_by_label`, `list_for_project`, `delete` |
| `CodingDecisionRepository` | `save`, `list_for_segment`, `list_for_code`, `list_for_project`, `delete` |
| `MemoRepository` | `save`, `list_for_entity`, `list_for_project` |
| `ClusterRepository` | `save_batch`, `list_for_project`, `get`, `mark_reviewed` |
| `ModelRunRepository` | `save`, `get`, `list_for_project` |
| `AISuggestionRepository` | `save_batch`, `list_for_segment`, `list_pending_for_project`, `update_status` |

#### Service protocols

`EmbeddingService` — `embed_and_store(segment_id, text)`, `embed_batch(items)`,
`find_similar(query, top_k, project_id)`, `get_all_embeddings(project_id)`.

`LLMService` — `model_name`, `suggest_codes(…)`, `find_similar_excerpts(…)`,
`propose_cluster_label(…)`, `synthesize_theme(…)`, `surface_contradictions(…)`.

`TranscriptImporter` — `can_import(path)`, `import_transcript(path, corpus_id)`.

`DocumentImporter` — `can_import(path)`, `import_document(path, corpus_id)`.

`EvidenceExporter` — `export(matrix, destination)`.

---

## 5. Application layer

The application layer contains use cases only. Use cases orchestrate
domain entities and infrastructure services; they contain no business
rules of their own and no persistence logic.

### 5.1 Ingestion use cases

**`IngestTranscriptUseCase`**

```
path (.transcript.json)
        │
        ▼  TranscriptImporter.can_import()
        │  TranscriptImporter.import_transcript()
        │         → Source, [Segment, …]
        │
        ▼  SourceRepository.save(source)
           SegmentRepository.save_batch(segments)
        │
        ▼  [if embed=True]
           EmbeddingService.embed_batch([(seg.id, seg.text), …])
           SegmentRepository.update_embedding_id(seg.id, emb_id)  × N
```

`execute_batch(paths, corpus_id, embed)` wraps `execute` in a loop,
catching and logging failures per file without aborting the batch.

**`RebuildEmbeddingsUseCase`**

Re-embeds all segments for a project in configurable batches (default 64).
Used when the embedding model changes or embeddings are missing.

### 5.2 Coding use cases

**`CreateCodeUseCase`**
Validates the label is unique within the project, creates a `Code` entity,
persists it. Raises `ValueError` if the label already exists.

**`ApplyCodeUseCase`**
Validates both segment and code exist, creates a `CodingDecision` with
`is_ai=False`, persists it.

**`SuggestCodesUseCase`**

```
segment_id
        │
        ▼  SegmentRepository.get(segment_id)
           CodeRepository.list_for_project(project_id)  → existing labels
        │
        ▼  LLMService.suggest_codes(text, existing_codes, context)
                → [{label, justification, confidence, is_new_code}, …]
        │
        ▼  ModelRun.create(…)  →  ModelRunRepository.save(run)
           AISuggestion.create(…) × N  →  AISuggestionRepository.save_batch([…])
        │
        ▼  returns [AISuggestion, …]  — all status=PENDING
```

`AcceptSuggestionUseCase` — loads a suggestion, creates a `CodingDecision`
with `is_ai=True` and `ai_run_id` set, updates suggestion status to ACCEPTED.

**`FindSimilarSegmentsUseCase`**
Calls `EmbeddingService.find_similar(query_text, top_k, project_id)`,
fetches segment text from the repo, returns `[{segment_id, text, speaker, score}]`.

### 5.3 Clustering use case

**`RunClusteringUseCase`**

```
project_id
        │
        ▼  EmbeddingService.get_all_embeddings(project_id)
                → [(segment_id, vector), …]
        │
        ▼  HDBSCAN(min_cluster_size, min_samples, metric)
                → labels[], probabilities[]
        │
        ▼  Group segment_ids by cluster label (skip label=-1 / noise)
        │
        ▼  [for each cluster]
           SegmentRepository.get(seg_id) × top_k  → representative excerpts
           LLMService.propose_cluster_label(excerpts, existing_categories)
                → {label, rationale, contradictions, confidence}
        │
        ▼  ModelRun.create(…)  →  ModelRunRepository.save(run)
           Cluster.create(…) × N  →  ClusterRepository.save_batch([…])
        │
        ▼  returns [Cluster, …] sorted by coherence_score descending
             all is_reviewed=False — waiting for analyst
```

HDBSCAN was chosen specifically because it: automatically determines the
number of clusters (no k parameter), assigns low-confidence points as
noise rather than forcing them into clusters, and handles uneven thematic
densities. These properties match the SRD requirement for "exploratory
clustering that tolerates uneven thematic densities and allows outlier
detection."

### 5.4 Export use cases

**`BuildEvidenceMatrixUseCase`**

Cross-references all `CodingDecision` records with segment text, speaker
metadata, source titles, and code labels. Supports `speaker_filter` and
`include_ai` options. Every row in the matrix carries full provenance:
source, segment index, analyst, timestamp, and `is_ai` flag.

**`ExportEvidenceMatrixCsvUseCase`** — serialises to UTF-8 CSV string.

**`ExportCodebookJsonUseCase`** — produces versioned JSON with all code
definitions, criteria, examples, and version history.

**`ExportAuditTrailUseCase`** — produces a chronologically ordered JSON
list of all coding decisions and model runs, suitable for methodological
appendices in academic research.

---

## 6. Infrastructure layer

The infrastructure layer contains all I/O — database, vector store,
LLM API calls, and file parsing. It is the only layer allowed to import
third-party libraries. No infrastructure class is ever exposed to the
domain or application layers directly; they communicate only through
the protocols defined in `domain/protocols.py`.

### 6.1 Relational database (SQLAlchemy)

**ORM models** (`infrastructure/db/models.py`):

12 tables, one per aggregate. All primary keys are UUID4 TEXT strings
for portability across SQLite and PostgreSQL. Timestamps are stored as
ISO-8601 strings. JSON blobs (lists, dicts) are stored as TEXT and
deserialised in the repository layer.

| Table | Maps to |
|---|---|
| `projects` | `Project` |
| `corpora` | `Corpus` |
| `sources` | `Source` |
| `segments` | `Segment` |
| `codes` | `Code` |
| `categories` | `Category` |
| `themes` | `Theme` |
| `coding_decisions` | `CodingDecision` |
| `memos` | `Memo` |
| `model_runs` | `ModelRun` |
| `ai_suggestions` | `AISuggestion` |
| `clusters` | `Cluster` |

**Repositories** (`infrastructure/db/repositories.py`):

10 `Sql*Repository` classes. Each is responsible for one aggregate and
translates bidirectionally between ORM rows and frozen domain entities.
Zero business logic. Zero cross-repository joins except where required
by the query (e.g. listing segments for a project requires joining
`segments → sources → corpora → projects`).

**Database selection:**

| Environment | Recommended | Why |
|---|---|---|
| Local laptop | `sqlite:///./thematic.db` | Zero setup, file-based |
| University server (multi-user) | `postgresql://…` | Concurrent writes, row-level locking |

The `DB_URL` in `.env` switches between them with no code changes.

### 6.2 Vector store (ChromaDB)

**`ChromaEmbeddingService`** (`infrastructure/embeddings/chroma_service.py`):

Wraps ChromaDB with a persistent local store and
`sentence-transformers` for embedding computation.

```
embed_and_store(segment_id, text)
        │
        ▼  SentenceTransformer.encode(text, normalize_embeddings=True)
           ChromaDB.upsert(id=segment_id, embedding=vector, metadata={project_id})
        │
        ▼  returns segment_id (used as embedding_id on Segment)

find_similar(query_text, top_k, project_id)
        │
        ▼  SentenceTransformer.encode(query_text)
           ChromaDB.query(embedding, n_results=top_k, where={project_id})
        │
        ▼  convert L2 distances → cosine similarity: score = 1 - (distance / 2)
           returns [(segment_id, score), …]
```

Embeddings are stored with L2 distance (ChromaDB `hnsw:space = l2`).
Cosine similarity is recovered by normalising embeddings before storage
(`normalize_embeddings=True`) and applying `score = 1 − d/2`.

**Recommended models:**

| Model | Size | Dims | Speed (CPU) | Notes |
|---|---|---|---|---|
| `paraphrase-multilingual-MiniLM-L12-v2` | 118 MB | 384 | ~200 seg/s | Default — good Spanish support |
| `paraphrase-multilingual-mpnet-base-v2` | 278 MB | 768 | ~80 seg/s | Better quality for university server |

### 6.3 LLM adapters

All LLM adapters satisfy the `LLMService` protocol and share the same
five public methods. Swapping from Ollama to Claude (or to any future
model) requires only changing which adapter is injected in `app.py`.

#### Prompt library (`infrastructure/llm/prompt_library.py`)

All prompts are pure functions — they accept structured arguments and
return rendered strings. No formatting logic lives in the adapters.
Centralising prompts satisfies two SRD requirements: reproducibility
(prompts are versioned with the code as `PROMPT_LIBRARY_VERSION`) and
auditability (the `prompt_hash` stored in every `ModelRun` links the
inference call back to the exact rendered prompt).

Five prompt pairs (system + user), one per LLM task:

| Task | Functions |
|---|---|
| Code suggestion | `suggest_codes_system()`, `suggest_codes_user(segment, codes, context)` |
| Cluster labelling | `propose_cluster_label_system()`, `propose_cluster_label_user(excerpts, categories)` |
| Theme synthesis | `synthesize_theme_system()`, `synthesize_theme_user(categories, excerpts, context)` |
| Contradiction surfacing | `surface_contradictions_system()`, `surface_contradictions_user(excerpts_by_source, question)` |
| Similar excerpts | `find_similar_excerpts_system()`, `find_similar_excerpts_user(reference, candidates)` |

All prompts instruct the model to return only valid JSON. All prompts
include the CRITICAL constraint that AI outputs are advisory only and
must never be silently adopted.

#### Ollama adapter — Tier 1 (interactive, local)

`OllamaLLMAdapter` (`infrastructure/llm/ollama_adapter.py`)

Calls a locally running Ollama server. Suitable for interactive tasks
where latency is visible to the analyst: per-segment code suggestions,
duplicate-code warnings, quick cluster labelling.

```
LLMService.suggest_codes(segment_text, existing_codes, context, project_id)
        │
        ▼  render prompt_library.suggest_codes_system() + suggest_codes_user(…)
           ollama.Client.chat(model, messages, options={temperature, num_predict})
        │
        ▼  ModelRun.create(task="suggest_codes", model_tier=LOCAL_FAST)
           json.loads(response.message.content)
        │
        ▼  returns [{label, justification, confidence, is_new_code}, …]
```

Retry: 2 attempts, 1-second wait (`tenacity`).

**Recommended models by hardware:**

| Model | RAM | Response time | Use when |
|---|---|---|---|
| `mistral:7b` | ~4 GB | 5–15 s | Default — good balance |
| `phi3:mini` | ~2.3 GB | 3–8 s | Fastest, light hardware |
| `mixtral:8x7b` | ~26 GB | 30–60 s | University server, best local quality |
| `mixtral:8x22b` | ~90 GB | varies | Server-class, massive corpus |

#### Claude API adapter — Tier 2 (synthesis, long-context)

`AnthropicLLMAdapter` (`infrastructure/llm/anthropic_adapter.py`)

Calls the Anthropic API. Best suited for tasks where context window
matters: theme synthesis across an entire corpus, cross-interview
contradiction surfacing, cluster labelling for large clusters.

```
LLMService.synthesize_theme(category_labels, supporting_excerpts, project_context)
        │
        ▼  render prompt_library.synthesize_theme_system() + synthesize_theme_user(…)
           anthropic.Anthropic.messages.create(
               model="claude-sonnet-4-6",
               max_tokens=4096,
               temperature=0.3,
               system=system_prompt,
               messages=[{role: "user", content: user_prompt}]
           )
        │
        ▼  ModelRun.create(task="synthesize_theme", model_tier=CLOUD, prompt_hash=sha256)
           json.loads(strip_markdown_fences(response.content[0].text))
        │
        ▼  returns {theme_label, narrative, evidence_summary, gaps}
```

Retry: 3 attempts, exponential backoff 2–30 seconds (`tenacity`).
Default model: `claude-sonnet-4-6`.

**Privacy note:** interview text leaves the local machine when this
adapter is called. For research with privacy-sensitive participants,
anonymise participant names in segments before calling any synthesis
method. Use Ollama for all interactive per-segment work.

### 6.4 Transcript importer

`TranscriptJsonImporter` (`infrastructure/importers/transcript_importer.py`)

The only coupling point between the two projects.

```python
def can_import(path: Path) -> bool
    # True iff: .transcript.json extension AND schema_version == "1.0"

def import_transcript(path: Path, corpus_id: str) -> tuple[Source, list[Segment]]
    # 1. Load and validate JSON (raises ValueError for bad schema version)
    # 2. Build Source from metadata block
    # 3. For each turn:
    #    - Apply speaker filter (INTERVIEWEE only by default)
    #    - Apply min_words filter (default: 3)
    #    - Average confidence across sub-segments
    #    - Segment.from_speaker_turn(…)
    # 4. Return (Source, [Segment, …])
```

Configuration:

| Parameter | Default | Effect |
|---|---|---|
| `min_words` | 3 | Skips filler utterances (Mm-hmm, Sí, Claro) |
| `include_interviewer` | `False` | By default imports only INTERVIEWEE turns for thematic analysis |

---

## 7. Presentation layer

The presentation layer is a Streamlit multi-page application.
`app.py` is the composition root — the only place concrete infrastructure
classes are instantiated and wired into session state.

### 7.1 Composition root (`app.py`)

```python
def _initialise_services() -> None:
    # Runs once per session; subsequent calls are no-ops
    if st.session_state.get("services_ready"): return

    settings = Settings()  # reads .env

    engine = create_engine(settings.db_url)
    Base.metadata.create_all(engine)          # creates tables on first run
    SessionLocal = sessionmaker(bind=engine)

    if settings.use_claude and settings.anthropic_api_key:
        llm = AnthropicLLMAdapter(api_key=settings.anthropic_api_key)
    else:
        llm = OllamaLLMAdapter(model=settings.ollama_model)

    st.session_state["llm"] = llm
    st.session_state["db_session_factory"] = SessionLocal
    st.session_state["services_ready"] = True
```

All pages access their dependencies through `st.session_state`, never
constructing infrastructure objects themselves.

### 7.2 Pages

| File | Route | Purpose |
|---|---|---|
| `app.py` | `/` | Landing page, status dashboard, quick-start guide |
| `01_corpus.py` | `/corpus` | Project and corpus management, transcript import |
| `02_immersion.py` | `/immersion` | Reading workspace, memos, bookmarks |
| `03_coding.py` | `/coding` | Segment browser, manual coding, AI suggestions |
| `04_codebook.py` | `/codebook` | Code CRUD, categories, theme management |
| `05_clusters.py` | `/clusters` | HDBSCAN cluster review, label editing, promotion |
| `06_comparison.py` | `/comparison` | Code frequency matrix, contradiction analysis, coverage gaps |
| `07_export.py` | `/export` | Evidence matrix, codebook, audit trail downloads |

---

## 8. AI assistance model — human oversight guarantee

Every AI-generated output passes through at least one of these three
barriers before it can influence the research record:

```
LLM inference call
        │
        ▼  ModelRun saved (model, task, prompt_hash, parameters, timestamp)
        │
        ▼  AISuggestion created with status = PENDING
        │
        │   ← analyst reads justification and excerpt
        │
        ▼  Analyst action required:
           ┌─────────────────────────────────────────┐
           │  ACCEPT → CodingDecision(is_ai=True)    │
           │  REVISE → CodingDecision(note=revision) │
           │  REJECT → AISuggestion.status=REJECTED  │
           └─────────────────────────────────────────┘
```

For clustering: clusters start as `is_reviewed=False`. Analyst must
review excerpts and explicitly confirm or revise the label before
`ClusterRepository.mark_reviewed()` is called.

For themes: `Theme.is_published` starts as `False`. Publishing requires
a non-empty `evidence_summary` and is a deliberate analyst action.

No AI output ever reaches the research record without a corresponding
`analyst` field identifying who reviewed and approved it.

---

## 9. Data flows

### 9.1 Full ingest pipeline

```
analyst runs: python scripts/import_transcripts.py ./output --project "…"
        │
        ▼  TranscriptJsonImporter.can_import(path)           ← format check
           TranscriptJsonImporter.import_transcript(path)    ← parse JSON
                → Source, [Segment × N]
        │
        ▼  SqlSourceRepository.save(source)
           SqlSegmentRepository.save_batch(segments)
        │
        ▼  ChromaEmbeddingService.embed_batch([(id, text), …])
                → SentenceTransformer.encode(texts)           ← model inference
                → ChromaDB.upsert(ids, embeddings, metadatas) ← vector store
        │
        ▼  SqlSegmentRepository.update_embedding_id(id, emb_id) × N
```

### 9.2 Coding session — AI-assisted

```
analyst opens segment in 03_coding.py
        │
        ▼  [manual] analyst selects code from multiselect → Apply button
           ApplyCodeUseCase.execute(segment_id, code_id, analyst)
                → CodingDecision(is_ai=False) persisted
        │
        ▼  [AI-assisted] analyst clicks "AI suggest"
           SuggestCodesUseCase.execute(segment_id, project_id, context)
                → OllamaLLMAdapter.suggest_codes(text, existing_codes, context)
                → [AISuggestion(status=PENDING), …] persisted
        │
        ▼  suggestions appear in UI with Accept / Reject buttons
           analyst reads justification, decides:
           Accept → CodingDecision(is_ai=True, ai_run_id=run.id) persisted
           Reject → AISuggestion.status = REJECTED
```

### 9.3 Clustering and theme synthesis

```
analyst clicks "Run clustering" in 05_clusters.py
        │
        ▼  ChromaEmbeddingService.get_all_embeddings(project_id)
           HDBSCAN(min_cluster_size, min_samples) → labels, probabilities
           [for each cluster]
             OllamaLLMAdapter.propose_cluster_label(excerpts, existing_categories)
             Cluster.create(label=proposed, is_reviewed=False) persisted
        │
        ▼  analyst reviews clusters, edits labels, clicks "Promote"
           ClusterRepository.mark_reviewed(cluster_id, category_id)
        │
        ▼  analyst clicks "Synthesise themes" in 05_clusters.py
           OllamaLLMAdapter.synthesize_theme(category_labels, excerpts, context)
                → {theme_label, narrative, evidence_summary, gaps}
        │
        ▼  analyst reviews draft, edits, creates Theme entity
           Theme.is_published starts False
           analyst publishes explicitly when satisfied with evidence
```

---

## 10. SOLID principles applied

### Single-Responsibility Principle

| Class | Sole responsibility |
|---|---|
| `TranscriptJsonImporter` | Parse one JSON format into domain entities |
| `ChromaEmbeddingService` | Store and retrieve vectors |
| `OllamaLLMAdapter` | Call Ollama, parse JSON response |
| `AnthropicLLMAdapter` | Call Claude API, parse JSON response |
| `prompt_library` module | Render prompt strings from structured arguments |
| `SqlSegmentRepository` | Persist and retrieve `Segment` entities |
| `IngestTranscriptUseCase` | Orchestrate import + embedding — nothing else |
| `SuggestCodesUseCase` | Request AI suggestions, persist as PENDING — nothing else |
| `RunClusteringUseCase` | Embed → cluster → label → persist — nothing else |
| `BuildEvidenceMatrixUseCase` | Assemble `EvidenceMatrix` from repositories — nothing else |

### Open/Closed Principle

Adding a new LLM provider: implement `LLMService` protocol, inject in `app.py`. Zero changes to any use case.

Adding a new import format (e.g. `.docx` field notes): implement `DocumentImporter` protocol. Zero changes to `IngestTranscriptUseCase`.

Adding a new export format: implement `EvidenceExporter` protocol. Zero changes to `BuildEvidenceMatrixUseCase`.

Adding a new embedding model: change one line in `.env`. Zero code changes.

### Liskov Substitution Principle

`SuggestCodesUseCase` accepts any `LLMService`. Passing `OllamaLLMAdapter`
or `AnthropicLLMAdapter` or a `MagicMock()` in tests all produce the same
observable behaviour. No use case knows which concrete adapter it received.

### Interface Segregation Principle

`LLMService` has five methods — each task-specific. A hypothetical adapter
that only supports code suggestion can satisfy the full protocol by raising
`NotImplementedError` on the other four, allowing partial adoption without
forcing a monolithic interface on every adapter.

`EmbeddingService` and `LLMService` are separate protocols even though
some systems (e.g. a hypothetical hosted endpoint) might support both.
Separating them lets the clustering use case depend only on `EmbeddingService`
without also depending on LLM inference.

### Dependency-Inversion Principle

Every use case receives its dependencies through its constructor as
protocol types, never as concrete classes. The composition root (`app.py`)
is the only place concrete classes are named. Tests can replace any
dependency with a `MagicMock` without patching.

---

## 11. Test architecture

```
tests/
├── unit/                      # 44 tests · 0.24 s · no model · no network · no GPU
│   ├── test_domain.py         # 25 tests
│   │   ├── Project, Corpus creation and immutability
│   │   ├── Segment.from_speaker_turn, from_paragraph
│   │   ├── Code defaults, unique IDs
│   │   ├── CodingDecision (manual and AI)
│   │   ├── EvidenceMatrix code_labels / source_titles
│   │   └── TranscriptJsonImporter (12 tests)
│   │       ├── can_import: valid file, wrong extension, wrong schema version
│   │       ├── import_transcript: source title, speaker filter,
│   │       │   include_interviewer flag, min_words filter, timestamps,
│   │       │   confidence averaging, Spanish characters, error handling
│   │       └── FileNotFoundError, ValueError for invalid JSON
│   │
│   └── test_use_cases.py      # 19 tests
│       ├── CreateCodeUseCase (3): save, duplicate label, project_id
│       ├── ApplyCodeUseCase (4): creates decision, missing segment/code, note
│       ├── SuggestCodesUseCase (7): returns suggestions, persistence,
│       │   model run saved, PENDING status, missing segment, empty response,
│       │   passes existing codes to LLM
│       ├── FindSimilarSegmentsUseCase (2): results with text, missing segment skipped
│       └── IngestTranscriptUseCase (3): saves source+segments, embed flag, format error
│
└── integration/               # (future) requires model download and real audio
    └── (placeholder)
```

**Testing principle:** every use case receives its dependencies through
the constructor. Tests inject `MagicMock` objects — no `monkeypatch`,
no real database, no real model. This is possible because the architecture
enforces dependency injection at every layer.

---

## 12. Security and privacy considerations

**Local-first defaults.** The default configuration (SQLite + ChromaDB +
Ollama) keeps all research data on the analyst's machine. The `ANTHROPIC_API_KEY`
field is empty by default; `USE_CLAUDE=false` keeps all inference local.

**No silent cloud calls.** Cloud API calls only happen when `USE_CLAUDE=true`
and a valid API key is set, or when the analyst explicitly selects Claude
as the LLM tier in the dashboard.

**Prompt hash for audit.** Every `ModelRun` stores a SHA-256 of the
concatenated system + user prompt. This allows post-hoc verification that
the model received exactly the intended prompt — no prompt injection can
occur silently.

**Analyst attribution on everything.** Every `CodingDecision` and `Memo`
carries a non-nullable `analyst` field. AI-origin decisions carry `is_ai=True`
and `ai_run_id` linking to the `ModelRun` record. Nothing in the research
record is anonymous or unattributed.

**Participant pseudonymisation.** `Participant.pseudonym` is the only name
field used in the analysis platform. The original audio file path is stored
in `Source.original_path` and `Source.import_metadata` for traceability,
but participant names from the transcript are not extracted — only speaker
role labels (`INTERVIEWER`, `INTERVIEWEE`).

---

## 13. Deployment profiles

### Local laptop (current hardware — i7-8565U, 12 GB RAM)

```bash
DB_URL=sqlite:///./thematic.db
OLLAMA_MODEL=mistral:7b
USE_CLAUDE=false
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

All Tier 1 features available. Theme synthesis with Claude API available
when `USE_CLAUDE=true` and a key is set.

### University server (64+ GB RAM, optional GPU)

```bash
DB_URL=postgresql://user:pass@localhost/thematic_db
OLLAMA_MODEL=mixtral:8x7b
USE_CLAUDE=false                     # fully offline if required
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
```

All three tiers available locally. Mixtral can handle large-batch cluster
labelling and long-context synthesis without leaving the institution's
network.

### Multi-analyst setup (university server + shared DB)

```bash
DB_URL=postgresql://user:pass@server/thematic_db
OLLAMA_HOST=http://server-ip:11434  # Ollama running on the server
```

Multiple analysts connect to the same PostgreSQL database and the same
Ollama server. Each analyst is identified by the `DEFAULT_ANALYST` setting
in their local `.env`. All decisions, memos, and model runs carry analyst
attribution.

---

## 14. Extension points

### Adding a new LLM provider

1. Create `thematic/infrastructure/llm/my_provider_adapter.py`
2. Implement all five `LLMService` protocol methods
3. In `app.py`, add a branch in `_initialise_services()` to instantiate it
4. No other files change

### Adding a new import format (e.g. interview grid, field note template)

1. Create `thematic/infrastructure/importers/my_format_importer.py`
2. Implement `can_import(path)` and `import_document(path, corpus_id)`
3. Register it in `01_corpus.py` alongside `TranscriptJsonImporter`
4. No domain or application changes required

### Adding a new export format

1. Add a class with `export(matrix, destination) -> Path` to `exporters/`
2. Wire it into `07_export.py`
3. No use case changes required

### Connecting to a new vector store (e.g. pgvector, FAISS)

1. Create `thematic/infrastructure/embeddings/my_store_service.py`
2. Implement `EmbeddingService` protocol
3. Inject it in `app.py` instead of `ChromaEmbeddingService`
4. No application or domain changes required
