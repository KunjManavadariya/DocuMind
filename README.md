# DocuMind

DocuMind is a documentation RAG workbench. Primary mode is local-first: app processes run on your laptop while managed backing services provide the real system boundaries:

- React frontend on `http://localhost:5173`
- FastAPI backend on `http://localhost:8000`
- Celery worker for async ingestion
- Neon Postgres with pgvector for documents, chunks, and vector search
- Upstash Redis for cache, Celery broker, and Celery result backend
- Cloudflare R2 for original uploaded or fetched source files
- Gemini for generation and embeddings

Optional public demo mode runs the React frontend as a Render Static Site and the FastAPI backend as a Render Docker web service. The Celery worker remains local for async ingestion demos.

## What It Does

- Upload `.txt`, `.md`, `.markdown`, or searchable `.pdf` documents.
- Fetch and ingest one documentation URL.
- Store original source files in R2.
- Chunk document text and embed chunks.
- Store metadata, chunks, and vectors in Neon pgvector.
- Ask questions against all indexed documents or selected documents.
- Generate grounded answers with citations.
- Show retrieved source chunks and similarity scores.
- Cache repeated embeddings and answers in Redis.
- Run async ingestion through Celery.
- Run eval cases against `top-1`, `top-3`, and `top-5` retrieval configs.
- Compare recall, MRR, context precision, faithfulness, and answer relevance.

## Quick Start

From repo root:

```bash
cp .env.example .env
```

Fill real values in `.env` only:

```env
DATABASE_URL=
REDIS_URL=
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=
CLOUDFLARE_R2_ENDPOINT_URL=
CLOUDFLARE_R2_ACCESS_KEY_ID=
CLOUDFLARE_R2_SECRET_ACCESS_KEY=
CLOUDFLARE_R2_BUCKET=
GEMINI_API_KEY=
```

For Upstash `rediss://` Celery URLs, keep SSL query string:

```env
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
```

Initialize Neon schema once:

```bash
docker compose -f docker-compose.managed-local.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
```

Start local app:

```bash
docker compose -f docker-compose.managed-local.yml up --build
```

Open:

```text
http://localhost:5173
```

Backend checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Stop:

```bash
docker compose -f docker-compose.managed-local.yml down
```

## Local Demo Settings

Keep these defaults for reliable laptop demos:

```env
INSTALL_ML_DEPS=false
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
DOCUMENT_STORAGE_PROVIDER=r2
```

Why: generation and embeddings use real Gemini APIs, while local eval and reranking avoid heavy `torch`, `ragas`, and `sentence-transformers` dependencies in Docker.

Optional heavy local ML mode:

```env
INSTALL_ML_DEPS=true
EVALUATION_PROVIDER=ragas
RERANKER_PROVIDER=cross-encoder
```

Use this only when you intentionally want RAGAS and cross-encoder reranking locally.

## Optional Render Demo

Render demo mode is meant for short portfolio demos, not always-on production uptime.

- Frontend URL: `https://documind-static-kunj.onrender.com`
- Backend URL: `https://documind-api-kunj.onrender.com`
- Frontend: Render Static Site from `frontend/`.
- Backend: Render Docker web service from `backend/Dockerfile`.
- Database/vector store: Neon Postgres with pgvector.
- Cache/broker: Upstash Redis.
- Source file storage: Cloudflare R2.
- LLM/embeddings: Gemini.
- Async worker: still local. Sync upload, URL ingestion, retrieval, answer generation, and eval can run through hosted frontend/backend. Async ingestion needs local worker connected to same Upstash/Neon/R2/Gemini env.

Render env needs same managed-service values as `.env`, plus:

```env
APP_ENV=render-free
CORS_ORIGIN_REGEX=https://.*\.onrender\.com
VITE_API_BASE_URL=https://YOUR_BACKEND_SERVICE.onrender.com
```

Deploy helper:

```bash
scripts/render-create-services.sh
```

The helper reads local `.env`, creates the backend Docker web service and frontend Static Site, and does not print secret values.

## Manual Browser Flow

1. Start local stack.
2. Open `http://localhost:5173`.
3. Confirm API URL is `http://localhost:8000`.
4. Upload a small document.
5. Turn `Async` on when you want to show Celery.
6. Click `Ingest`.
7. Watch indexed document and chunk counts.
8. Ask a factual question from the document.
9. Inspect citations and source chunks.
10. Select one document to scope retrieval.
11. Open `Eval`.
12. Run default eval cases or edit `Cases JSON`.

## Documentation

Detailed project docs live in `docs/`:

- `docs/system-design.md`: architecture, data flow, design choices, failure modes.
- `docs/managed-services.md`: Neon, Upstash, R2, Gemini, and local provider choices.
- `docs/local-managed-runbook.md`: setup, start, verify, demo, stop, debug.
- `docs/demo-checklist.md`: step-by-step technical walkthrough script.
- `docs/code-map.md`: feature-to-file map for frontend, backend, providers, and tests.

## API Flow

Ingest text:

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

Retrieve chunks:

```bash
curl -X POST http://localhost:8000/query/retrieve \
  -H "Content-Type: application/json" \
  -d '{"question": "What stores embeddings?", "top_k": 5}'
```

Generate cited answer:

```bash
curl -X POST http://localhost:8000/query/answer \
  -H "Content-Type: application/json" \
  -d '{"question": "What stores embeddings?", "top_k": 5}'
```

Upload file:

```bash
curl -X POST "http://localhost:8000/documents/upload?chunk_size=256&chunk_overlap=40" \
  -F "file=@/path/to/your/document.md"
```

Fetch URL:

```bash
curl -X POST http://localhost:8000/documents/ingest-url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/docs/page",
    "chunk_size": 256,
    "chunk_overlap": 40
  }'
```

Async ingest:

```bash
curl -X POST http://localhost:8000/documents/ingest-text-async \
  -H "Content-Type: application/json" \
  -d '{
    "title": "DocuMind Notes",
    "content": "FastAPI serves the API. Redis powers Celery. pgvector stores embeddings."
  }'
```

Poll job:

```bash
curl http://localhost:8000/documents/jobs/<task_id>
```

List corpus:

```bash
curl http://localhost:8000/documents
```

Clear corpus:

```bash
curl -X DELETE http://localhost:8000/documents
```

Run eval:

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

## Explanation

DocuMind is not only a chatbot. It is a complete local RAG workbench: ingestion, chunking, embeddings, pgvector retrieval, reranking, grounded generation, citations, caching, async jobs, document scoping, and eval.

The app processes run locally because this project is a technical RAG workbench, not an always-on customer product. There are no active users requiring public uptime, so running paid cloud instances continuously would add cost without improving the core system. Managed services stay because they are the important architecture boundaries: Neon for vector persistence, Upstash for queue/cache, R2 for durable source files, and Gemini for model calls.

`/health` proves FastAPI is alive. `/ready` proves the backend can reach Neon and Upstash.

The answer endpoint is separate from retrieval on purpose. `/query/retrieve` exposes raw retrieved chunks for debugging and eval. `/query/answer` uses those chunks to generate cited prose.

Eval dashboard exists because RAG quality cannot depend on vibes. It compares retrieval configs using recall, MRR, and context precision, then scores generated answers for faithfulness and relevance.

## Verification

```bash
pytest
cd frontend && npm run build
docker compose -f docker-compose.managed-local.yml config
```

Smoke test with running stack:

```bash
scripts/smoke-local-managed.sh
```
