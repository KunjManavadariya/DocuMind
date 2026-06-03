# DocuMind

DocuMind is a RAG documentation assistant that ingests docs, retrieves relevant chunks with citations, and includes an evaluation dashboard for comparing retrieval and answer quality.

## Current Milestone

Foundation plus first retrieval core:

- FastAPI backend with `/health` and `/ready`
- Release-readiness gate at `/release/readiness`
- React frontend that calls the backend health endpoint
- Docker Compose for backend, frontend, Postgres/pgvector, Redis, and Celery worker
- CI skeleton for backend tests and frontend build
- Text ingestion endpoint: `POST /documents/ingest-text`
- URL ingestion endpoint: `POST /documents/ingest-url`
- File upload ingestion endpoint: `POST /documents/upload` for `.txt`, `.md`, `.markdown`, and searchable `.pdf`
- Source document storage abstraction:
  - local filesystem storage for development
  - Cloudflare R2-compatible storage for release
- Corpus management endpoints:
  - `GET /documents`
  - `DELETE /documents`
- Async ingestion endpoints backed by Celery:
  - `POST /documents/ingest-text-async`
  - `POST /documents/ingest-url-async`
  - `POST /documents/upload-async`
  - `GET /documents/jobs/{task_id}`
- Similarity retrieval endpoint: `POST /query/retrieve`
- Grounded answer endpoint with citations: `POST /query/answer`
- Retrieval and answer-quality evaluation endpoint: `POST /eval/run`
- Optional document-id scoping for retrieval, answers, and evals
- Reranking provider boundary with deterministic local reranking
- Eval dashboard in the frontend for comparing retrieval and answer-quality configs
- Deterministic local embeddings for offline tests and development
- Optional Gemini answer generation via `GENERATION_PROVIDER=gemini`
- Optional Gemini embeddings via `EMBEDDING_PROVIDER=gemini`
- Redis-backed JSON caching for embeddings and repeated answer responses

## Local Development

Primary local-only demo with managed services:

```bash
cp .env.managed-local.example .env
docker compose -f docker-compose.managed-local.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
docker compose -f docker-compose.managed-local.yml up --build
```

Then open:

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- Backend readiness: http://localhost:8000/ready

This mode runs the backend, worker, and frontend on your laptop while using Neon, Upstash, Cloudflare R2, and Gemini from `.env`. See `docs/local-managed-runbook.md`.

Run the local managed smoke test:

```bash
scripts/smoke-local-managed.sh
```

Use `docs/demo-checklist.md` before a walkthrough.

Fully offline/local Docker defaults are still available:

```bash
cp .env.example .env
docker compose up --build
```

Local Docker builds use lean backend dependencies by default. When you intentionally enable production RAGAS or cross-encoder reranking, build with optional ML dependencies:

```bash
INSTALL_ML_DEPS=true docker compose build api worker
docker compose up -d api worker
```

Then open:

- Frontend: http://localhost:5173
- Backend health: http://localhost:8000/health
- Backend readiness: http://localhost:8000/ready
- Release readiness: http://localhost:8000/release/readiness

The frontend supports document upload, async ingestion polling, indexed corpus inspection, corpus clearing, cited answers, source inspection, recent answer history, and retrieval plus answer-quality eval comparison.

Environment and hosting references:

- `.env.managed-local.example`
- `docker-compose.managed-local.yml`
- `docs/local-managed-runbook.md`
- `docs/demo-checklist.md`
- `scripts/smoke-local-managed.sh`
- optional public-hosting references:
- `.env.production.example`
- `render.yaml`
- `docs/render-deployment.md`
- `docs/ec2-provisioning.md`
- `docs/managed-services.md`
- `docs/production-checklist.md`
- `docker-compose.prod.yml`
- `.github/workflows/deploy-ec2.yml`

## First Retrieval Flow

Once Docker is available and the stack is running, ingest text:

```bash
curl -X POST http://localhost:8000/documents/ingest-text \
  -H "Content-Type: application/json" \
  -d '{
    "title": "DocuMind Notes",
    "content": "FastAPI serves the API. Redis powers Celery. pgvector stores embeddings.",
    "chunk_size": 80,
    "chunk_overlap": 10
  }'
```

Then retrieve relevant chunks:

```bash
curl -X POST http://localhost:8000/query/retrieve \
  -H "Content-Type: application/json" \
  -d '{"question": "What stores embeddings?", "top_k": 5}'
```

To restrict retrieval to selected documents, include `document_ids`:

```bash
curl -X POST http://localhost:8000/query/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What stores embeddings?",
    "top_k": 5,
    "document_ids": ["<document_id>"]
  }'
```

Or generate a cited answer from retrieved chunks:

```bash
curl -X POST http://localhost:8000/query/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "What stores embeddings?", "top_k": 5}'
```

Or upload a document:

```bash
curl -X POST "http://localhost:8000/documents/upload?chunk_size=256&chunk_overlap=40" \
  -F "file=@/path/to/your/document.md"
```

Or fetch and index a single documentation URL:

```bash
curl -X POST http://localhost:8000/documents/ingest-url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/docs/page",
    "chunk_size": 256,
    "chunk_overlap": 40
  }'
```

For production-style ingestion, enqueue work asynchronously:

```bash
curl -X POST http://localhost:8000/documents/ingest-text-async \
  -H "Content-Type: application/json" \
  -d '{
    "title": "DocuMind Notes",
    "content": "FastAPI serves the API. Redis powers Celery. pgvector stores embeddings."
  }'
```

Then poll job status:

```bash
curl http://localhost:8000/documents/jobs/<task_id>
```

Inspect the indexed local corpus:

```bash
curl http://localhost:8000/documents
```

Clear the local demo corpus before a clean manual test:

```bash
curl -X DELETE http://localhost:8000/documents
```

Check whether the current environment is production-deployable:

```bash
curl http://localhost:8000/release/readiness
```

Local development is expected to return `deployable: false` because it uses Docker-local Postgres/Redis, local model/eval providers, localhost CORS, and missing Cloudflare R2 settings.

## Interview Explanation

The first milestone intentionally proves service boundaries before adding AI complexity. FastAPI, React, Postgres/pgvector, Redis, and Celery are all present from day one so the local system mirrors the eventual production architecture. This prevents a common project failure mode: building a local-only prototype that must be redesigned during deployment.

`/ready` and `/release/readiness` are intentionally separate. `/ready` answers "can this running container talk to its dependencies right now?" `/release/readiness` answers "is this environment configured like a production deployment?" That lets local development stay convenient while making release blockers explicit before EC2 deployment.

The second milestone adds the retrieval core before answer generation. This is deliberate: RAG quality depends first on whether the system can chunk documents, embed chunks, store vectors, and retrieve the right context. The local hash embedding provider is only for deterministic offline development; the provider boundary lets us swap in Gemini or OpenAI embeddings without rewriting ingestion or retrieval.

Upload ingestion supports plain text, Markdown, and searchable PDFs. Searchable PDF support uses `pypdf`; scanned PDFs that contain images rather than embedded text would require OCR, which is intentionally deferred until the core RAG path is stable.

URL ingestion currently fetches and indexes one HTTP/HTTPS page. HTML is converted into readable text while ignoring script/style content. Full website crawling is intentionally deferred because crawlers need stricter limits, robots-policy decisions, duplicate handling, and rate controls.

The answer endpoint is separate from the retrieval endpoint on purpose. `/query/retrieve` exposes the raw context for debugging and evaluation, while `/query/answer` converts that same context into a cited answer. This makes retrieval quality visible instead of hiding it behind LLM prose.

Gemini generation is available behind the same answer-generator interface. Local generation remains the default because it keeps tests deterministic and avoids requiring API keys during development. To use Gemini:

```bash
GENERATION_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
```

The Gemini integration uses Google’s current `google-genai` Python SDK pattern: `from google import genai`, then `client.models.generate_content(...)`.

Gemini embeddings are also available behind the embedding-provider interface:

```bash
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=your_google_ai_studio_key
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=384
```

The pgvector schema uses `VECTOR(384)`. Gemini’s embedding API supports `output_dimensionality`, so we request 384-dimensional embeddings to keep local and Gemini providers compatible with the same database column.

Caching is enabled by default:

```bash
CACHE_ENABLED=true
REDIS_URL=redis://redis:6379/0
EMBEDDING_CACHE_TTL_SECONDS=86400
ANSWER_CACHE_TTL_SECONDS=600
```

DocuMind caches embeddings at the provider layer and full answer responses at the `/query/answer` layer. Answer cache entries are invalidated whenever new documents are ingested because the underlying knowledge base may have changed.

Uploaded source documents are stored before indexing. Local development writes them under `LOCAL_DOCUMENT_STORAGE_DIR`; production should use Cloudflare R2:

```bash
DOCUMENT_STORAGE_PROVIDER=r2
CLOUDFLARE_R2_ENDPOINT_URL=your_r2_endpoint
CLOUDFLARE_R2_ACCESS_KEY_ID=your_access_key
CLOUDFLARE_R2_SECRET_ACCESS_KEY=your_secret_key
CLOUDFLARE_R2_BUCKET=your_bucket
```

Those values are environment-only. They should not be committed to the repo.

Async ingestion uses Celery with Redis as the broker/result backend. The API returns a task ID immediately, and the worker performs chunking, embedding, pgvector writes, and answer-cache invalidation in the background.

Corpus management is included because retrieval quality depends on the active corpus. During demos and eval runs, old documents can pollute top-k results. `GET /documents` makes the indexed state visible, and `DELETE /documents` gives the operator a clean reset path while also invalidating cached answers.

Document-id scoping is the next step beyond clearing the corpus. The UI lets the operator select indexed documents, and those IDs are sent to retrieve, answer, and eval requests. This keeps manual tests and eval runs focused without deleting other indexed documents.

The evaluation layer measures both retrieval quality and generated answer quality:

```bash
curl -X POST http://localhost:8000/eval/run \
  -H "Content-Type: application/json" \
  -d '{
    "cases": [
      {
        "id": "vectors",
        "question": "Where are embeddings stored?",
        "expected_terms": ["pgvector", "embeddings"]
      }
    ],
    "configs": [
      {"name": "top-1", "top_k": 1},
      {"name": "top-5", "top_k": 5}
    ]
  }'
```

Current retrieval metrics include recall@k, mean reciprocal rank, and context precision. Answer metrics include local deterministic faithfulness and answer relevance scores. The frontend Eval tab runs the same endpoint against editable eval cases and compares `top-1`, `top-3`, and `top-5`.

The local answer scorer is intentionally deterministic for demos and tests. For release, `EVALUATION_PROVIDER=ragas` is required by the readiness gate so the same dashboard can move toward RAGAS-style faithfulness and answer relevancy scoring with a real evaluator model.

Production RAGAS evaluation uses Gemini by default:

```bash
EVALUATION_PROVIDER=ragas
GEMINI_API_KEY=your_google_ai_studio_key
RAGAS_LLM_MODEL=gemini-2.0-flash
RAGAS_EMBEDDING_MODEL=gemini-embedding-001
```

This mirrors the rest of DocuMind's provider design: local providers keep development stable and credential-free, while production providers are activated through environment configuration.

Retrieval uses a two-stage shape: pgvector returns a larger candidate pool, then the reranker reorders candidates before the final `top_k` is returned. Local development uses deterministic lexical reranking. Production readiness expects `RERANKER_PROVIDER=cross-encoder` with `cross-encoder/ms-marco-MiniLM-L-6-v2`, which we will enable when deployment resources are ready.

## Verification

```bash
.venv/bin/python -m pytest
cd frontend && npm run build
```
