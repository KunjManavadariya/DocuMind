# Local Managed Runbook

This is the primary operating guide for DocuMind. It explains how to start, verify, use, stop, and debug the local-managed runtime.

## Runtime Model

Nothing is deployed to a public host. Your laptop runs:

- FastAPI backend
- Celery worker
- React frontend

Managed services provide real backing systems:

- Neon Postgres with pgvector
- Upstash Redis
- Cloudflare R2
- Gemini

This split is intentional. App containers are cheap and local. Data, queue state, files, and model calls live in managed systems where they belong.

## 1. Prepare Environment

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

Do not commit `.env`.

Why: `.env` contains secrets. The repo keeps only `.env.example` so configuration shape is documented without exposing credentials.

## 2. Required Local Defaults

Use these values unless intentionally testing heavy local ML:

```env
APP_ENV=local-managed
INSTALL_ML_DEPS=false
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
DOCUMENT_STORAGE_PROVIDER=r2
VITE_API_BASE_URL=http://localhost:8000
```

Why:

- Gemini generation gives real answer behavior.
- Gemini embeddings give real semantic retrieval.
- Local eval keeps eval fast and deterministic.
- Local reranker avoids heavy cross-encoder dependencies.
- R2 keeps original source files outside containers.
- Vite frontend talks to local FastAPI.

## 3. Upstash URL Detail

For Upstash `rediss://` Celery URLs, include SSL query string:

```env
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
```

Why: Celery uses Redis transport and needs TLS certificate behavior in the URL. Normal `REDIS_URL` ping can work while Celery still fails if this query string is missing.

## 4. Initialize Neon Schema

Run once after filling `DATABASE_URL`:

```bash
docker compose -f docker-compose.managed-local.yml run --rm api \
  python -m app.db_cli ensure-schema --env-file .env
```

Expected result:

```text
schema ready
```

Why: Neon must have pgvector extension, document tables, chunk tables, and vector index before ingestion is trusted.

## 5. Start Local Stack

```bash
docker compose -f docker-compose.managed-local.yml up --build
```

What starts:

- `api`: FastAPI backend with reload
- `worker`: Celery worker
- `frontend`: Vite dev server

Open:

```text
http://localhost:5173
```

Why `--build`: it makes Docker rebuild when dependencies or Dockerfiles changed.

## 6. Verify Backend

Health:

```bash
curl http://localhost:8000/health
```

Meaning:

- API process is alive.
- FastAPI app loaded.
- This does not prove database or Redis connectivity.

Readiness:

```bash
curl http://localhost:8000/ready
```

Meaning:

- API can connect to Neon.
- API can ping Upstash Redis.
- This is the stronger local demo check.

## 7. Run Smoke Test

With stack running:

```bash
scripts/smoke-local-managed.sh
```

What it checks:

1. `/health`
2. `/ready`
3. text ingestion
4. scoped retrieval
5. cited answer generation
6. eval endpoint

Why: this validates the full RAG loop from API to DB/cache/model/eval path.

## 8. Browser Demo Flow

1. Open frontend.
2. Confirm API URL field says:

```text
http://localhost:8000
```

3. Upload `.txt`, `.md`, `.markdown`, or searchable `.pdf`.
4. Turn `Async` on to show Celery worker path.
5. Click `Ingest`.
6. Wait for indexed document and chunk counts.
7. Ask a factual question from the document.
8. Inspect answer citations.
9. Inspect source snippets and scores.
10. Select one document in corpus list.
11. Ask again to show scoped retrieval.
12. Open eval dashboard.
13. Run default eval cases.

Why this order:

- corpus first, because RAG needs evidence
- ask second, because it proves user workflow
- source inspection third, because it proves grounding
- eval last, because it proves measurement

## 9. Stop Stack

```bash
docker compose -f docker-compose.managed-local.yml down
```

What stops:

- API container
- worker container
- frontend container

What remains:

- Neon data
- Upstash cache/task state
- R2 source files
- Gemini key in local `.env`

Why: stopping local containers should not destroy managed data.

## 10. Clean Stale Containers

Use only if Docker state gets stale:

```bash
docker compose -f docker-compose.managed-local.yml down --remove-orphans
```

Do not delete Neon/R2 data unless you intentionally want a fresh corpus.

## 11. Common Issues

### Frontend Says Offline

Check:

```bash
curl http://localhost:8000/health
```

Likely causes:

- API container not running
- frontend API URL changed
- backend crashed on startup due missing env

### Upload Fails

Likely causes:

- unsupported file type
- scanned PDF has no embedded text
- R2 credentials wrong
- Gemini embedding call failed
- database schema not initialized

### Async Job Never Finishes

Check worker logs:

```bash
docker compose -f docker-compose.managed-local.yml logs worker
```

Likely causes:

- Celery cannot connect to Upstash
- SSL query string missing
- worker missing env values
- embedding provider failed

### Retrieval Gives Weak Answer

Check:

- document actually indexed
- selected document scope
- source chunks shown in UI
- query phrasing
- eval metrics

Why: generation quality depends on retrieved context. If retrieved chunks are weak, answer will be weak.

### Eval Shows Misses

Likely causes:

- expected terms not present in indexed chunk text
- top-k too low
- wrong document scope selected
- document content not related to default eval cases

Fix:

- edit `Cases JSON` for current document
- select correct document
- compare `top-1`, `top-3`, `top-5`

## 12. Optional Heavy ML Mode

Use only when specifically needed:

```env
INSTALL_ML_DEPS=true
EVALUATION_PROVIDER=ragas
RERANKER_PROVIDER=cross-encoder
```

Then rebuild:

```bash
docker compose -f docker-compose.managed-local.yml build api worker
```

Why this is off by default: `ragas`, `sentence-transformers`, and `torch` can make Docker builds slow and large, especially on Apple Silicon.

## Explanation

I chose local-only runtime because this project is a technical RAG workbench, not an always-on customer product. There are no active users requiring public uptime, so continuously running paid cloud instances would add cost without improving the core system.

The application processes remain containerized, so the runtime is reproducible. Neon, Upstash, R2, and Gemini stay managed because they are core boundaries: persistent vector database, Redis queue/cache, durable source storage, and model providers.

`/ready` is the key health check for this mode because it proves the local backend can reach managed dependencies.
