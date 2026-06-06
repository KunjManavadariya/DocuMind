# Demo Checklist

Use this before a demo or technical walkthrough. It is intentionally operational: follow it in order and the system should be in a clean, explainable state.

## 1. Start

For hosted demo, open:

```text
https://documind-rag-workbench.onrender.com
```

For local demo, start Docker:

```bash
docker compose -f docker-compose.managed-local.yml up -d
```

Why: detached mode starts API, worker, and frontend while keeping terminal free for checks.

## 2. Verify Containers

```bash
docker compose -f docker-compose.managed-local.yml ps
```

Expected:

- API running
- worker running
- frontend running

If API is unhealthy, inspect:

```bash
docker compose -f docker-compose.managed-local.yml logs api
```

If worker is failing, inspect:

```bash
docker compose -f docker-compose.managed-local.yml logs worker
```

## 3. Verify API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Meaning:

- `/health`: FastAPI process is alive.
- `/ready`: FastAPI can reach Neon and Upstash.

Why both: process health and dependency readiness are different. A running API is not useful if it cannot reach database/cache.

## 4. Run Full Smoke Test

```bash
scripts/smoke-local-managed.sh
```

This verifies:

- health
- readiness
- ingestion
- retrieval
- cited answer
- eval

Why: it proves the main RAG path before opening the UI.

## 5. Open UI

```text
http://localhost:5173
```

Confirm API URL:

```text
http://localhost:8000
```

If URL differs, edit field and click `Save`.

## 6. Corpus Walkthrough

Use corpus panel to explain:

- `Select document`: local source file enters system.
- URL input: single web page can be fetched and indexed.
- `Async`: switches ingestion from direct API work to Celery background job.
- `Ingest`: starts file ingestion.
- status row: shows ready, loading, queued, success, or error.
- `docs`: indexed document count.
- `chunks`: searchable chunk count.
- document checkboxes: limit retrieval/eval to chosen documents.
- `Clear Corpus`: reset indexed corpus and answer cache.

Strong explanation:

> Corpus is the active knowledge base. RAG answer quality depends on what corpus is indexed and what document scope is selected.

## 7. Ask Walkthrough

Ask a factual question from uploaded document.

Explain:

- question is embedded
- pgvector retrieves similar chunks
- reranker reorders candidates
- Gemini generates answer from retrieved context
- citations map answer back to source chunks
- source panel exposes retrieved evidence
- cache hit means Redis served repeated answer

Strong explanation:

> I keep sources visible because RAG output should be inspectable. If answer looks wrong, first debug retrieval, not prompt wording.

## 8. Eval Walkthrough

Open Eval tab and run default cases or edit `Cases JSON`.

Explain:

- cases are test questions
- expected terms define retrieval target
- configs compare `top_k` values
- recall shows whether evidence was found
- MRR shows how early correct evidence appeared
- context precision shows how much retrieved context was useful
- faithfulness checks answer support from context
- relevance checks whether answer addresses question

Strong explanation:

> Eval turns RAG quality from opinion into measurement. It helps tune chunk size, top-k, reranking, and prompts.

## Talking Points

### Architecture

> DocuMind runs app processes locally in Docker: FastAPI API, React frontend, and Celery worker. It uses managed services for real backing systems: Neon for Postgres plus pgvector, Upstash Redis for cache and Celery broker/results, Cloudflare R2 for durable source files, and Gemini for generation and embeddings.

### Why Render Plus Local Worker

> DocuMind hosts the frontend as a Render Static Site and the backend as a Render Docker Web Service. The Celery worker remains local for async demos because there is no always-on background workload. This gives public access for sync RAG workflows while keeping compute cost low.

### Why Docker

> Docker keeps local runs reproducible. The demo does not depend on my laptop's Python or Node environment; the app containers define the runtime.

### Why Neon And pgvector

> pgvector lets Postgres store vector embeddings next to document metadata. For this project scale, it keeps retrieval simple without adding a separate vector database.

### Why Redis And Upstash

> Redis handles two roles: caching repeated answers/embeddings and powering Celery async ingestion. Upstash gives managed Redis without running a local Redis server.

### Why R2

> The database stores chunks and embeddings, while R2 stores original source documents. That separation keeps large source files outside Postgres and preserves artifacts for possible re-indexing.

### Why Gemini

> Gemini is used through provider boundaries for generation and embeddings. Local providers remain for deterministic tests, while Gemini gives real semantic behavior in the demo.

### Why Local Eval And Rerank

> Full RAGAS and cross-encoder reranking pull heavy ML dependencies locally. For a reliable laptop demo, Gemini generation/embeddings stay real while eval and rerank stay lightweight. Heavy providers remain configurable.

## Stop

```bash
docker compose -f docker-compose.managed-local.yml down
```

Why: local containers stop, but Neon, Upstash, R2, and Gemini-backed data/config remain intact.
