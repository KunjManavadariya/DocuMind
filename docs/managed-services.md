# Managed Local Services

DocuMind runs app containers locally, but uses managed backing services. Set them up in this order.

## 1. Neon Postgres

Create a Neon project with Postgres and pgvector support.

Use:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

Initialize schema:

```bash
docker compose -f docker-compose.managed-local.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
```

Why first: ingestion and retrieval depend on vector storage.

## 2. Upstash Redis

Create one Upstash Redis database.

Use:

```env
REDIS_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CACHE_ENABLED=true
```

Why second: Redis powers answer/embedding cache and Celery async ingestion.

## 3. Cloudflare R2

Create R2 bucket and access keys.

Use:

```env
DOCUMENT_STORAGE_PROVIDER=r2
CLOUDFLARE_R2_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=documind
```

Why third: source files should stay outside app containers. Postgres stores searchable chunks; R2 stores original artifacts.

## 4. Gemini

Create Gemini API key.

Use:

```env
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=384
```

Why fourth: question answering and semantic retrieval need model provider credentials.

## 5. Local Eval And Reranking

Use default lightweight settings:

```env
INSTALL_ML_DEPS=false
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
```

Why: local demos stay fast and reliable. Heavy RAGAS/cross-encoder mode remains available when intentionally enabled.

## Explanation

I kept app processes local and managed services external. That gives a realistic RAG architecture without public hosting: Neon owns vector persistence, Upstash owns cache and queue state, R2 owns source document durability, and Gemini owns model calls.
