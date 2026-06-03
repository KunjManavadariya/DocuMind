# DocuMind System Design

This document captures how DocuMind scales beyond the single-user portfolio deployment.

## Initial Scope

The production release starts with one EC2 instance running Docker Compose for the API, worker, frontend, and Nginx. Managed external services handle persistence: Neon for Postgres/pgvector, Cloudflare R2 for source documents, and Upstash Redis for cache and Celery broker.

## Interview Explanation

The single-instance version is intentionally simple enough to ship, but the service boundaries match a scalable architecture. FastAPI is stateless, ingestion work is isolated in Celery, vectors live outside the app container, source documents live in object storage, and Redis handles short-lived cache and queue state.

Source files and vector chunks are intentionally separate. Cloudflare R2 stores original uploaded documents, while Neon pgvector stores extracted chunks and embeddings. This lets the system preserve the user artifact, rebuild indexes later, and keep retrieval storage optimized for search rather than raw file durability.

## Scale Path to 10k Users

The first public release can run on one EC2 instance because the app is still portfolio-scale. The service boundaries are chosen so each bottleneck can move independently later.

### API

FastAPI should stay stateless. At higher traffic, run multiple API containers behind a load balancer. Session state should not live in process memory; cache and queue state already live in Redis.

### Ingestion

Document ingestion is already isolated in Celery. Scale workers separately from API containers when uploads increase. For large documents, add queue priorities, retry limits, dead-letter handling, and per-user ingestion quotas.

### Storage

Source files stay in Cloudflare R2. Vector chunks stay in Postgres/pgvector. This split lets us reprocess documents without asking users to re-upload files.

For 10k users, add:

- users
- workspaces
- document collections
- document-level ACLs
- collection filters in retrieval
- per-workspace quotas

### Retrieval

Current retrieval is two-stage: vector search first, reranking second. At higher scale, keep a candidate limit, cache repeated query embeddings, and measure p95 retrieval latency. If pgvector becomes a bottleneck, move hot collections to a dedicated vector service or shard by workspace.

### Caching

Redis caches embeddings and answer responses. Cache keys include document scope, provider config, and reranker config to avoid cross-document leakage.

### Evaluation

Eval runs should stay separate from user chat traffic. For large eval jobs, run them as background tasks and store results so dashboards load historical runs rather than recomputing every page view.

### Observability

Production needs structured logs, request IDs, latency metrics, worker queue depth, cache hit rate, and error alerts. Minimum useful metrics:

- API p50/p95 latency
- retrieval latency
- generation latency
- Celery queue depth
- ingestion success/failure count
- Redis cache hit rate
- Postgres connection count

### Security

Only Nginx is public. API, worker, Redis, and Postgres ports are private. Secrets live in environment variables on the deployment host or a secret manager. Uploaded documents need workspace-level authorization before download or retrieval.
