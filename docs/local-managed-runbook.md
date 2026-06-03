# Local Managed Runbook

Use this as the primary DocuMind demo path.

Nothing is deployed to a public host. Your laptop runs:

- FastAPI backend
- Celery worker
- React frontend

Managed services provide real backing systems:

- Neon Postgres with pgvector
- Upstash Redis for cache, Celery broker, and result backend
- Cloudflare R2 for source document storage
- Gemini for generation and embeddings

## 1. Prepare Env

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

For Upstash `rediss://` Celery URLs, include the SSL query string:

```env
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
```

Do not commit `.env`.

## 2. Recommended Local Mode

Keep these values for smooth local demos:

```env
INSTALL_ML_DEPS=false
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
DOCUMENT_STORAGE_PROVIDER=r2
```

Why: Gemini generation and embeddings still use real managed AI, while local eval and reranking avoid heavy PyTorch/RAGAS dependencies that make laptop Docker builds slow and large.

## 3. Full ML Optional

Use this only when you specifically want RAGAS and cross-encoder reranking locally:

```env
INSTALL_ML_DEPS=true
EVALUATION_PROVIDER=ragas
RERANKER_PROVIDER=cross-encoder
```

Why: this installs `ragas`, `sentence-transformers`, and `torch`. On Apple Silicon Docker/Linux, this can pull very large ML wheels and take several minutes or more.

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

## Explanation

I chose local-only runtime because this project is a technical RAG workbench, not an always-on customer product. There are no active users requiring public uptime, so continuously running paid cloud instances would add cost without improving the core system. The application processes remain containerized, so the runtime is reproducible: API, worker, and frontend run through Docker Compose. I kept Neon, Upstash, R2, and Gemini as managed services because they are the important boundaries: persistent vector database, Redis queue/cache, durable source storage, and model providers.

`/ready` is the key health check for this mode because it proves the local backend can reach managed dependencies.
