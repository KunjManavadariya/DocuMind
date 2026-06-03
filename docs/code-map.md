# Code Map

This guide maps DocuMind features to files. Use it when explaining where behavior lives and why the code is split this way.

## Frontend

### `frontend/src/App.jsx`

Main UI component.

Owns:

- health state
- API base URL state
- file upload state
- URL ingest state
- async polling state
- corpus list
- selected document scope
- ask view
- eval view
- recent answer history

Why one main component:

- app is a focused workbench, not a large multi-page product
- most state is shared between sidebar, ask view, and eval view
- keeping it together makes demo behavior easy to trace

When it would split later:

- auth added
- multiple pages added
- persisted eval runs added
- workspace management added

### `frontend/src/api.js`

Thin API wrapper.

Owns:

- base URL normalization
- `localStorage` persistence for API URL
- shared `fetch` error handling
- request functions for health, documents, upload, URL ingest, ask, and eval

Why separate file:

- UI components stay focused on state and rendering
- backend paths are centralized
- error handling is consistent

### `frontend/src/styles.css`

All visual styling.

Owns:

- app shell layout
- sidebar layout
- forms and buttons
- answer surface
- source list
- eval dashboard grid
- responsive behavior

Why CSS file instead of component library:

- project needs one polished custom workbench
- fewer dependencies
- easier to control dense technical UI

## Backend API

### `backend/app/main.py`

FastAPI route layer.

Owns:

- app creation
- CORS setup
- singleton provider instances
- `/health`
- `/ready`
- document endpoints
- query endpoints
- eval endpoint

Why route layer is thin:

- route functions validate HTTP payloads and call services
- ingestion, retrieval, generation, storage, and eval logic live in separate modules
- tests can patch service boundaries cleanly

### `backend/app/schemas.py`

Pydantic request/response models.

Owns:

- upload/ingest payload shapes
- document summaries
- retrieve request/response
- answer request/response
- citation shape
- eval case/config/result shapes

Why schemas matter:

- API responses stay predictable
- frontend knows exact JSON shape
- invalid payloads fail early

## Ingestion

### `backend/app/document_loaders.py`

Turns uploaded files or URLs into text.

Supports:

- `.txt`
- `.md`
- `.markdown`
- searchable `.pdf`
- single HTTP/HTTPS page

Why searchable PDF only:

- embedded text extraction is lighter and deterministic
- scanned PDF OCR would add heavy dependencies and complexity

### `backend/app/chunking.py`

Splits text into overlapping chunks.

Default:

- `chunk_size=256`
- `chunk_overlap=40`

Why:

- chunks must be small enough for focused retrieval
- overlap protects context at chunk boundaries

### `backend/app/ingestion.py`

Orchestrates document ingestion.

Flow:

1. validate overlap
2. chunk text
3. embed chunks
4. ensure schema
5. store document and chunks

Why separate:

- same ingestion logic is used by sync API and Celery worker
- route code does not duplicate chunk/embed/store behavior

### `backend/app/worker.py`

Celery worker entrypoint.

Owns:

- Celery app config
- async ingestion task
- cache invalidation after ingestion

Why:

- long ingestion work moves out of request path
- frontend can poll task status

## Storage And Database

### `backend/app/db.py`

Database access layer.

Owns:

- schema creation
- document insertion/upsert
- chunk insertion
- corpus listing
- corpus clearing
- vector retrieval

Why:

- SQL is isolated from API route code
- pgvector query stays in one place
- document filtering is handled consistently

### `backend/app/storage.py`

Source file storage abstraction.

Providers:

- local filesystem
- Cloudflare R2-compatible object storage

Why:

- raw source files and vector chunks have different storage needs
- object storage preserves artifacts while database serves retrieval

## Model And Retrieval

### `backend/app/embeddings.py`

Embedding provider abstraction.

Providers:

- local hash embeddings for deterministic tests
- Gemini embeddings for real semantic behavior
- cached wrapper using Redis

Why:

- tests should not require model credentials
- demo should use real embeddings
- repeated embeddings should be cached

### `backend/app/reranking.py`

Reranker abstraction.

Providers:

- no-op
- local lexical reranker
- optional cross-encoder reranker

Why:

- vector search is good first-stage retrieval
- reranking improves final ordering
- local mode stays lightweight

### `backend/app/generation.py`

Answer generation abstraction.

Providers:

- local grounded generator for tests
- Gemini generator for real answers

Why:

- route logic does not depend directly on Gemini SDK
- local tests remain deterministic
- prompt is centralized

## Cache

### `backend/app/cache.py`

JSON cache abstraction.

Providers:

- Redis cache
- in-memory cache for tests
- null cache

Why:

- repeated answers and embeddings should avoid repeated model calls
- cache can be disabled or replaced without changing route logic

## Evaluation

### `backend/app/evaluation.py`

Retrieval and answer eval engine.

Owns:

- running cases across configs
- recall@k
- MRR
- context precision
- matched terms
- first matching rank

Why:

- eval uses same retrieval path as normal ask flow
- metrics make retrieval tuning measurable

### `backend/app/answer_evaluation.py`

Answer-quality evaluator.

Providers:

- local deterministic evaluator
- optional RAGAS evaluator

Why:

- retrieval quality and answer quality are different
- answer can sound good while being unsupported

## Tests

### `backend/tests`

Test coverage includes:

- chunking
- document loading
- storage
- embeddings
- generation
- retrieval/reranking
- evaluation
- worker behavior
- API endpoints
- cache behavior

Why:

- provider boundaries need regression coverage
- local deterministic providers make tests credential-free

## Scripts

### `scripts/smoke-local-managed.sh`

End-to-end local smoke test.

Checks:

- API health
- readiness
- ingest
- retrieve
- answer
- eval

Why:

- unit tests prove modules
- smoke test proves running stack wiring
