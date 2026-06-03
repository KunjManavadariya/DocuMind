# Managed Local Services

DocuMind runs API, worker, and frontend locally, but depends on managed services for persistence, cache/queue, object storage, and model calls. This document explains what each service does, why it was picked, what values are needed, and how it fits into the whole system.

## Service Order

Set services up in this order:

1. Neon Postgres
2. Upstash Redis
3. Cloudflare R2
4. Gemini
5. Local eval and reranking mode

This order matches dependency depth. Database comes first because ingestion cannot store chunks without it. Redis comes second because cache and async jobs depend on it. R2 comes third because source files should be preserved before indexing. Gemini comes fourth because generation and embeddings need model credentials. Eval/rerank mode comes last because it controls local resource weight.

## 1. Neon Postgres With pgvector

### What It Stores

Neon stores:

- document metadata
- source URI
- content hash
- chunk text
- token counts
- embeddings
- pgvector index

### Why Neon

Neon gives managed Postgres without running a local database. This matters because the app should not lose corpus data when Docker containers stop. It also keeps the demo close to a real deployment shape: app containers are disposable, while database state lives outside them.

### Why pgvector

pgvector lets Postgres store embeddings and run vector similarity search. For DocuMind scale, this is simpler than adding a separate vector database. Metadata and vectors stay together, which makes document filtering straightforward.

### Required Env

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require
```

### Schema Initialization

Run once after `.env` is filled:

```bash
docker compose -f docker-compose.managed-local.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
```

This creates:

- `vector` extension
- `documents`
- `document_chunks`
- document ID index
- ivfflat vector index

### Why Schema Init Exists

Routes can lazily call schema setup, but explicit initialization is cleaner. It confirms database access before the demo and prevents first-upload confusion.

## 2. Upstash Redis

### What It Does

Redis has two roles:

- cache layer
- Celery broker/result backend

Embedding cache avoids repeated embedding calls for identical text. Answer cache avoids repeated generation for identical question/scope/provider config. Celery broker/result backend lets the frontend enqueue ingestion and poll status.

### Why Upstash

Upstash gives managed Redis without a local Redis container. That keeps state available across local app restarts and avoids running another service on the laptop.

### Required Env

```env
REDIS_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0?ssl_cert_reqs=CERT_REQUIRED
CACHE_ENABLED=true
```

### Why Celery URLs Need SSL Query

Upstash uses TLS. Celery Redis transport needs SSL certificate behavior specified in the URL. Without `?ssl_cert_reqs=CERT_REQUIRED`, Celery can fail even if normal Redis ping works.

### Cache TTLs

```env
EMBEDDING_CACHE_TTL_SECONDS=86400
ANSWER_CACHE_TTL_SECONDS=600
```

Embedding TTL is longer because same text embedding is stable. Answer TTL is shorter because answers depend on current corpus and generation behavior.

## 3. Cloudflare R2

### What It Stores

R2 stores original uploaded files and fetched source bytes. Postgres stores extracted chunks, not the full source artifact.

### Why R2

Object storage is the correct home for files. Source documents can be large, binary, or needed later for re-indexing. Keeping them in R2 avoids bloating Postgres and separates durable artifact storage from retrieval storage.

### Required Env

```env
DOCUMENT_STORAGE_PROVIDER=r2
CLOUDFLARE_R2_ENDPOINT_URL=https://ACCOUNT_ID.r2.cloudflarestorage.com
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=documind
```

### How It Aligns With Retrieval

When a document is uploaded:

1. raw file goes to R2
2. extracted text is chunked
3. chunks and embeddings go to Neon
4. R2 URI is stored with document metadata
5. citations can point back to original source location

## 4. Gemini

### What It Does

Gemini handles:

- document embeddings
- query embeddings
- grounded answer generation

### Why Gemini

DocuMind needs real semantic behavior. Local hash embeddings are useful for deterministic tests, but Gemini embeddings make retrieval meaningful for natural language questions. Gemini generation produces fluent answers while the backend constrains it to retrieved context.

### Required Env

```env
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=384
GEMINI_TEMPERATURE=0.2
```

### Why 384 Dimensions

The database vector column is created as `VECTOR(384)`. Gemini embedding API supports output dimensionality, so DocuMind requests 384-dimensional vectors. This keeps local and Gemini providers compatible with the same schema.

### Why Low Temperature

Temperature `0.2` keeps answers more stable and less creative. A RAG assistant should prioritize grounded accuracy over expressive variation.

## 5. Local Eval And Reranking

### Default Env

```env
INSTALL_ML_DEPS=false
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
RERANKER_CANDIDATE_MULTIPLIER=4
```

### Why Local Eval

Local eval gives deterministic, fast feedback during demos. It checks expected term matching, faithfulness heuristics, and answer relevance heuristics without downloading large ML packages.

### Why Local Reranker

Local reranker uses lexical overlap to reorder pgvector candidates. It is not as strong as a cross-encoder, but it is stable, lightweight, and enough to demonstrate two-stage retrieval.

### Optional Heavy Mode

```env
INSTALL_ML_DEPS=true
EVALUATION_PROVIDER=ragas
RERANKER_PROVIDER=cross-encoder
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

This installs large dependencies such as `torch`, `sentence-transformers`, and `ragas`. Keep it off unless specifically testing heavy local ML.

## Why Not Run Everything Locally

Running Postgres, Redis, object storage, and models locally would reduce external dependencies, but it would also make the system less representative of real RAG architecture. DocuMind keeps app processes local but leaves durable services external. This gives a practical balance:

- low compute cost
- reproducible local containers
- persistent managed data
- real model behavior
- no paid always-on app hosting

## Troubleshooting

### `/ready` Fails

Check:

- `DATABASE_URL`
- `REDIS_URL`
- network access
- Neon project active
- Upstash Redis active

### Upload Fails

Check:

- R2 endpoint
- R2 bucket name
- access key ID
- secret access key
- `DOCUMENT_STORAGE_PROVIDER=r2`

### Async Ingestion Stays Queued

Check:

- worker container running
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- Upstash SSL query string

### Answers Fail

Check:

- `GEMINI_API_KEY`
- `GENERATION_PROVIDER=gemini`
- indexed corpus exists
- selected document scope is not empty by mistake

## Explanation

DocuMind keeps local app runtime and managed service boundaries separate. Local Docker gives control and no always-on hosting cost. Neon, Upstash, R2, and Gemini keep the parts that should not live inside app containers: persistent vectors, queue/cache state, source artifacts, and model intelligence.
