# Local Managed Runbook

Use this as the primary DocuMind demo path.

Nothing is deployed to a public host. Your laptop runs:

- FastAPI backend
- Celery worker
- React frontend

Managed services still provide production-like backing systems:

- Neon Postgres with pgvector
- Upstash Redis for cache, Celery broker, and result backend
- Cloudflare R2 for source document storage
- Gemini for generation, embeddings, and RAGAS evaluation

## 1. Prepare Env

From repo root:

```bash
cp .env.managed-local.example .env
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

## 2. Recommended Full Local Mode

Keep these values for full local feature mode:

```env
INSTALL_ML_DEPS=true
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=ragas
RERANKER_PROVIDER=cross-encoder
DOCUMENT_STORAGE_PROVIDER=r2
```

Why: this keeps the demo closest to production architecture while still running all app processes locally.

## 3. Lean Fallback

If Docker build is too slow or memory-heavy, use:

```env
INSTALL_ML_DEPS=false
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
```

Why: Gemini generation and embeddings still work, but RAGAS and cross-encoder are skipped.

## 4. Initialize Neon Schema

Run once after filling `DATABASE_URL`:

```bash
docker compose -f docker-compose.managed-local.yml run --rm api \
  python -m app.db_cli ensure-schema --env-file .env
```

Why: Neon stores documents, chunks, and pgvector embeddings. Schema must exist before ingestion.

## 5. Start Local Stack

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

Expected:

```text
/health = app process is up
/ready = backend can reach Neon and Upstash
```

## 6. Demo Flow

1. Open frontend.
2. Confirm API URL field says:

```text
http://localhost:8000
```

3. Upload `.txt`, `.md`, `.markdown`, or searchable `.pdf`.
4. Keep `Async` on to show Celery worker.
5. Ask document questions.
6. Open eval dashboard and run default eval cases.

## 7. Stop Stack

```bash
docker compose -f docker-compose.managed-local.yml down
```

Why: this stops laptop containers but keeps Neon, Upstash, R2, and Gemini credentials/data intact.

## 8. Clean Local Containers

Use only if Docker gets stale:

```bash
docker compose -f docker-compose.managed-local.yml down --remove-orphans
```

Do not delete Neon/R2 data unless you intentionally want a fresh corpus.

## Interview Explanation

I chose local-only deployment because the goal is reliable demonstration without paying for always-on hosting. The application processes remain containerized, so the runtime is still reproducible: API, worker, and frontend run through Docker Compose. I kept Neon, Upstash, R2, and Gemini as managed services because they are the important production boundaries: persistent vector database, Redis queue/cache, durable source storage, and model providers. This gives a production-shaped architecture without public hosting cost.

`/ready` is the key health check for this mode because it proves the local backend can reach managed dependencies. `/release/readiness` may remain false because this is not a public production release: localhost CORS and local-only process hosting are intentional.
