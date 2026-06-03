# Managed Services Setup

Set up services in this order. Each step gives one env block.

## 1. Neon Postgres

Create Neon project with Postgres. Enable pgvector if Neon project does not already provide it.

Copy pooled or direct connection string into:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Validate:

```bash
python -m app.db_cli ensure-schema --env-file .env
python -m app.release_cli --env-file .env
```

Why first: ingestion and retrieval depend on vector storage. Without Postgres/pgvector, the app cannot preserve chunks or run search.

## 2. Upstash Redis

Create Redis database. For clean production isolation, prefer three Redis databases:

- cache
- Celery broker
- Celery result backend

If using one Redis database for budget reasons, use same URL for all three initially:

```env
REDIS_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0
CACHE_ENABLED=true
```

Why second: API answers use cache, and async ingestion uses Celery broker/result backend.

## 3. Cloudflare R2

Create R2 bucket and API token/access keys.

Use:

```env
DOCUMENT_STORAGE_PROVIDER=r2
CLOUDFLARE_R2_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=documind
```

Why third: original source files should live outside the app container. pgvector stores chunks; R2 stores durable source artifacts.

## 4. Gemini

Create Gemini API key.

Use:

```env
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=ragas
GEMINI_API_KEY=...
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
RAGAS_LLM_MODEL=gemini-2.0-flash
RAGAS_EMBEDDING_MODEL=gemini-embedding-001
```

Why fourth: local providers let deployment wiring happen without model credentials. Production uses Gemini for answers/embeddings and RAGAS evaluation.

## 5. Reranker

Use:

```env
INSTALL_ML_DEPS=true
RERANKER_PROVIDER=cross-encoder
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Why last: cross-encoder reranking improves final context ordering, but it is heavy. Enable after base production services are working.

## 6. Domain

Use:

```env
CORS_ORIGINS=https://your-domain.com
VITE_API_BASE_URL=https://your-domain.com/api
```

Rebuild frontend after changing `VITE_API_BASE_URL` because Vite reads it at build time.

## 7. Final Validation

Inside backend container:

```bash
python -m app.release_cli --env-file .env
```

Via API:

```bash
curl http://localhost/api/release/readiness
```

Required:

```json
{"deployable": true}
```

## Interview Explanation

I wired production dependencies in dependency order: database first because it is the retrieval source of truth, Redis second because it powers caching and async jobs, object storage third for durable source documents, model credentials fourth for generation/evaluation, and reranking last because it is valuable but heavyweight. That order reduces debugging noise because each layer has one clear responsibility.
