# Demo Checklist

Use this before a demo or technical walkthrough.

## Start

```bash
docker compose -f docker-compose.managed-local.yml up -d
```

Verify:

```bash
docker compose -f docker-compose.managed-local.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/ready
scripts/smoke-local-managed.sh
```

Open:

```text
http://localhost:5173
```

## Browser Flow

1. Confirm API URL is `http://localhost:8000`.
2. Upload a small `.txt`, `.md`, `.markdown`, or searchable `.pdf`.
3. Turn `Async` on when you want to show Celery worker ingestion.
4. Ask a factual question from the uploaded document.
5. Point out citations and source snippets.
6. Switch to eval dashboard.
7. Run eval and explain retrieval/answer metrics.

## Talking Points

Architecture:

> DocuMind runs app processes locally in Docker: FastAPI API, React frontend, and Celery worker. It uses managed services for real backing systems: Neon for Postgres plus pgvector, Upstash Redis for cache and Celery broker/results, Cloudflare R2 for durable source files, and Gemini for generation and embeddings.

Why local-only:

> I chose local-only runtime because the demo does not need always-on public uptime. This avoids idle hosting cost while keeping the real system boundaries: database, queue/cache, object storage, and model provider.

Why Docker:

> Docker keeps local runs reproducible. The demo does not depend on my laptop's Python or Node environment; the app containers define the runtime.

Why Neon and pgvector:

> pgvector lets Postgres store vector embeddings next to document metadata. For this project scale, it keeps retrieval simple and production-relevant without adding a separate vector database.

Why Redis/Upstash:

> Redis handles two roles: caching repeated answers/embeddings and powering Celery async ingestion. Upstash gives managed Redis without running a local Redis server.

Why R2:

> The database stores chunks and embeddings, while R2 stores original source documents. That separation keeps large source files outside Postgres.

Why Gemini:

> Gemini is used through provider boundaries for generation and embeddings. Local providers still exist for deterministic tests and fallback mode.

Why local eval/rerank by default:

> Full RAGAS and cross-encoder reranking pull heavy ML dependencies locally. For a reliable laptop demo, I keep Gemini generation/embeddings real and use local lightweight evaluation/reranking. The heavier providers remain configurable.

Health checks:

> `/health` proves the API process is alive. `/ready` proves the API can reach Neon and Upstash.

## Stop

```bash
docker compose -f docker-compose.managed-local.yml down
```
