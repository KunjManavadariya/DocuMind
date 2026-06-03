# DocuMind Build Notes

These notes track the major implementation decisions in interviewer-friendly language.

## Step 1: Production-Shaped Foundation

We started with service boundaries instead of AI features:

- FastAPI backend
- React frontend
- Postgres with pgvector
- Redis
- Celery worker
- Docker Compose
- GitHub Actions CI

Why: a RAG app is not just a prompt. The production system needs API serving, background ingestion, vector persistence, cache/queue state, and frontend workflows. By creating those boundaries first, each later feature lands in the same place it will live in production.

Interview version:

> I deliberately built the local architecture to mirror production. The API is stateless, ingestion work is isolated in a worker, vectors live in pgvector, and Redis handles cache and queue state. That kept the project from becoming a local-only prototype.

## Step 2: Retrieval Before Generation

We added:

- Text chunking
- Deterministic local embeddings
- Document and chunk tables
- pgvector similarity retrieval
- `/documents/ingest-text`
- `/documents/upload`
- `/query/retrieve`
- `/query/answer`

Why: in RAG, answer quality is downstream of retrieval quality. If the right chunks are not retrieved, the LLM cannot reliably produce grounded answers. So we verify chunking, embedding, storage, and retrieval before adding answer generation.

The local embedding provider is temporary. It exists so tests can run without API keys, billing, network access, or model nondeterminism. The code uses an embedding-provider boundary so Gemini/OpenAI embeddings can be added later without changing the retrieval pipeline.

We also moved ingestion into a service layer instead of keeping it inside route handlers. That gives file upload, future URL crawling, Cloudflare R2 storage, and Celery background jobs one shared path for chunking, embedding, and persistence.

Searchable PDFs are parsed with `pypdf`. This handles normal text-based PDFs while keeping the dependency footprint small. OCR for scanned PDFs is a separate capability and would add more infrastructure and processing cost, so it is deferred.

Interview version:

> I separated retrieval from generation because RAG failures are often retrieval failures disguised as model failures. First I built and tested chunking, embedding, vector storage, and top-k retrieval. Only after that would I add the LLM answer layer and citations.

## Step 3: Grounded Answers With Citations

We added:

- An answer-generation provider boundary
- A deterministic local grounded answer generator
- A grounded prompt builder for the future LLM integration
- `/query/answer`
- Citation metadata returned separately from the answer text

Why: the app needs cited answers, but we should not hide retrieval behavior. `/query/retrieve` remains available for debugging and evaluation; `/query/answer` uses the same retrieved chunks to produce the user-facing response.

The local generator is intentionally simple. It proves the answer response shape, citation mapping, and no-source behavior without needing API keys. The prompt builder defines the contract the future LLM must follow: answer only from supplied context and use inline citation markers.

Interview version:

> I kept retrieval and answer generation as separate layers. The retrieval endpoint lets me inspect and evaluate the actual context, while the answer endpoint turns that context into a cited response. That separation is important because it makes RAG failures diagnosable instead of treating the LLM as a black box.

## Step 4: Gemini Generation Provider

We added:

- `google-genai`
- `GeminiAnswerGenerator`
- `create_answer_generator(settings)`
- `GENERATION_PROVIDER=local|gemini`
- Mocked SDK tests so CI does not call external APIs

Why: the app needs real LLM generation, but production providers should sit behind an interface. The local generator stays as the default for deterministic development and tests; Gemini can be enabled with environment variables when a real API key is available.

We selected `gemini-2.5-flash-lite` as the default Gemini generation model because Google’s current model docs list it as the stable Flash-Lite model optimized for cost efficiency and high throughput. The SDK integration follows the current official Python pattern using `from google import genai` and `client.models.generate_content(...)`.

Interview version:

> I kept the LLM provider swappable. Local generation is the test fallback, and Gemini is the production provider. This lets CI run without secrets while production can use a real model by changing environment variables instead of application logic.

## Step 5: Gemini Embedding Provider

We added:

- `GeminiEmbeddingProvider`
- `create_embedding_provider(settings)`
- `EMBEDDING_PROVIDER=local|gemini`
- Gemini `embed_content` calls with `output_dimensionality`
- Separate embedding task types:
  - `RETRIEVAL_DOCUMENT` for stored chunks
  - `RETRIEVAL_QUERY` for questions

Why: embeddings are a provider concern, not ingestion or retrieval business logic. The ingestion service only asks for document embeddings; the query path only asks for query embeddings. This lets us switch from deterministic local embeddings to Gemini embeddings without rewriting storage or retrieval.

We kept pgvector at `VECTOR(384)` and configured Gemini to return 384-dimensional vectors. That matters because pgvector dimensions are fixed at the column level; letting providers return arbitrary dimensions would break inserts or query comparisons.

Interview version:

> I treated embeddings as a swappable provider. Local hash embeddings keep tests deterministic, while Gemini embeddings can be enabled for production. I fixed the pgvector column at 384 dimensions and used Gemini’s output dimensionality option so both providers fit the same vector schema.

## Step 6: Redis Caching

We added:

- `RedisJsonCache`
- `InMemoryJsonCache` for tests
- Stable SHA-256 cache keys
- Cached embeddings through `CachedEmbeddingProvider`
- Cached `/query/answer` responses
- `cache_hit` on answer responses
- Answer-cache invalidation on document ingestion

Why: embeddings and repeated answers are expensive compared with cache lookups. Caching embeddings avoids repeated model calls for the same chunk or query. Caching full answers helps repeated questions return quickly.

The cache is JSON-based so it can store both vectors and structured API responses. Redis failures fail open: if Redis is unavailable, the app computes normally instead of taking down the query path. That is important for graceful degradation.

We invalidate cached answers when documents are ingested because the answer cache depends on the current knowledge base. Embeddings do not require the same invalidation because their key includes the exact text, provider, task type, and vector dimension.

Interview version:

> I cached at two levels: embeddings and final answers. Embedding cache keys include provider, dimension, task type, and text, so they are safe to reuse. Answer cache entries are cleared on ingestion because the document corpus changed. Redis is treated as an optimization, not a hard dependency, so cache failures degrade to normal computation.

## Step 7: Async Ingestion With Celery

We added:

- `documind.ingest_text` Celery task
- JSON task serialization
- Task result backend support
- `POST /documents/ingest-text-async`
- `POST /documents/upload-async`
- `GET /documents/jobs/{task_id}`

Why: ingestion can be slow because it may involve document extraction, chunking, model embedding calls, and database writes. The API should not block the request thread while that happens. Instead, it validates/extracts input, enqueues a Celery task, and returns a task ID immediately.

The worker uses the same ingestion service as the synchronous endpoints. That keeps behavior consistent: both paths chunk, embed, store, and invalidate answer cache in the same way.

Interview version:

> I moved long-running ingestion behind Celery. The API returns a task ID immediately, while the worker handles chunking, embeddings, pgvector writes, and cache invalidation. This keeps the request path responsive and gives the frontend a clear processing-to-ready workflow.

## Step 8: Frontend Chat And Upload Workflow

We added:

- Upload UI for `.txt`, `.md`, `.markdown`, and `.pdf`
- Async ingestion mode
- Job polling
- Question input
- Cited answer display
- Source inspection
- Recent answer history

Why: the backend is only useful if the workflow is visible. The first frontend version focuses on the core operator loop: add docs, wait for indexing, ask a question, inspect citations. It avoids decorative landing-page work because this is a tool, not a marketing site.

The UI keeps ingestion and question-answering visually separate. That mirrors the backend architecture: documents enter through ingestion, while questions go through retrieval and generation. Sources are always shown next to the answer so grounding remains visible.

Interview version:

> I built the frontend around the actual RAG workflow instead of a landing page. Users upload docs, track ingestion, ask questions, and inspect sources. Showing sources next to answers reinforces the main product promise: answers are grounded in retrieved documentation.

## Step 9: Retrieval Evaluation Harness

We added:

- `eval/testset.json`
- `backend/app/evaluation.py`
- `POST /eval/run`
- Config comparison by `top_k`
- Per-case recall@k
- Mean reciprocal rank
- Mean context precision

Why: before measuring answer quality, we need to know whether retrieval finds the right context. If retrieval misses the relevant chunk, a generated answer will either be wrong, vague, or unsupported. The first evaluation layer therefore measures retrieval directly.

This is not the final RAGAS dashboard yet. It is the foundation for it: a testset format, metric result schema, and config comparison endpoint. Once the dashboard is built and real LLM generation is active, RAGAS-style faithfulness and answer relevance can be added on top.

Interview version:

> I built an evaluation harness before polishing the chat UI further. It compares retrieval configs and reports recall@k, MRR, and context precision. That lets me discuss retrieval quality with numbers instead of just showing a chatbot response.

## Step 10: Eval Dashboard

We added:

- Frontend Eval tab
- Editable eval cases JSON
- `top-1`, `top-3`, and `top-5` comparison
- Metric cards for recall, MRR, and context precision
- Per-case pass/miss table with first matching rank and matched terms

Why: the backend eval endpoint gives raw metrics, but a product demo needs those metrics to be visible. The dashboard makes retrieval quality inspectable without leaving the app. It also makes tradeoffs clear: increasing `top_k` can preserve recall while lowering context precision because extra unrelated chunks enter the prompt.

This is intentionally retrieval-focused. If retrieval cannot find the right evidence, answer-level evaluation is not very meaningful. Once retrieval is stable, we can add answer faithfulness, answer relevance, and groundedness checks on top.

Interview version:

> I added an eval dashboard so retrieval quality is visible in the product, not just in terminal output. It compares top-k settings using recall, MRR, and context precision, then shows which cases passed or missed. That helps tune the retriever before spending effort on LLM answer evaluation.

## Step 11: Corpus Management

We added:

- `GET /documents`
- `DELETE /documents`
- Indexed document/chunk counts in the frontend
- Recent indexed document list in the sidebar
- Clear Corpus action
- Answer-cache invalidation when the corpus is cleared

Why: after adding the eval dashboard, we saw the next real product issue: retrieval searched across every indexed local document. That is correct for a global corpus, but it makes demos and manual evals noisy when old files remain in Postgres. Corpus management makes the hidden retrieval state visible and gives us a clean reset path before testing a document.

This is not the final multi-tenant data model. Production will likely need users, workspaces, collections, document-level filtering, and permissions. But this step gives us an operator control that is useful immediately and points directly toward that production design.

Interview version:

> The eval dashboard exposed corpus pollution: old documents could appear in top-k results. I added corpus visibility and a clear-corpus path so manual tests and eval runs start from a known state. In production, I would evolve this into workspace or collection scoping with document-level filters and access control.

## Step 12: Scoped Retrieval

We added:

- Optional `document_ids` on `/query/retrieve`
- Optional `document_ids` on `/query/answer`
- Optional `document_ids` on `/eval/run`
- pgvector retrieval filtering by selected document IDs
- Answer-cache keys that include document scope
- Frontend document checkboxes for Ask and Eval scope

Why: clearing the corpus solves demo hygiene, but it is not how a production system should handle mixed document sets. Real users need to ask questions against a specific document, folder, workspace, or collection while leaving other documents indexed. Document-id scoping gives us the first version of that behavior.

The cache key includes the selected document IDs because the same question can have different correct answers depending on scope. Without scope in the key, an answer generated for one document could be incorrectly reused for another document.

Interview version:

> After making corpus state visible, I added scoped retrieval. The same question can mean different things in different documents, so retrieve, answer, and eval requests now accept document IDs. I also included scope in the answer-cache key to prevent cross-document cache leakage. This is the foundation for production workspace or collection filtering.

## Step 13: Release Readiness Gate

We added:

- `backend/app/release.py`
- `GET /release/readiness`
- Checks for production environment, public CORS origins, non-local Postgres, non-local Redis/Celery, enabled cache, Gemini-backed model providers, Gemini API key, and Cloudflare R2 settings
- Tests for local failure and production-shaped success

Why: runtime health is not the same as deployability. A local Docker stack can be healthy while still being wrong for release because it points at local Postgres/Redis, uses local deterministic providers, or lacks object-storage credentials. The release-readiness gate makes those blockers explicit.

This also gives us a practical production checklist. Each failed check maps directly to a deployment task: switch to Neon, switch to Upstash, configure Gemini, configure R2, and replace localhost CORS with the public frontend origin.

Interview version:

> I separated runtime readiness from release readiness. `/ready` proves the container can reach its current dependencies. `/release/readiness` proves the environment is configured for production: managed DB, managed Redis, real model provider, R2 object storage, public CORS, and caching. That prevents shipping a demo-configured system by accident.

## Step 14: Source Document Storage

We added:

- `backend/app/storage.py`
- `DocumentStorage` protocol
- `LocalDocumentStorage` for local development
- `R2DocumentStorage` for Cloudflare R2-compatible production storage
- upload endpoints that store the raw file before indexing
- stored source URIs passed into the ingestion pipeline
- storage tests for local writes and R2 `put_object`

Why: indexed chunks are not the same thing as source documents. Chunks are optimized for retrieval and embeddings; source files are the durable user artifact. Production needs both: pgvector for search and object storage for the original PDF/Markdown/text file.

Local storage keeps development credential-free. R2 storage is behind env vars, so the code is production-capable without committing secrets. When we switch to production, the only change should be environment configuration, not route logic.

Interview version:

> I separated source storage from vector indexing. The original uploaded document is stored in object storage, while extracted chunks and embeddings go to Postgres/pgvector. That mirrors production RAG architecture: object storage preserves the source artifact, vector storage serves retrieval, and both are linked by source URI metadata.

## Step 15: URL Ingestion

We added:

- `fetch_url_document`
- HTML text extraction for fetched pages
- URL fetch timeout and max-size settings
- `POST /documents/ingest-url`
- `POST /documents/ingest-url-async`
- frontend URL input in the Corpus panel
- tests for URL loading and URL ingestion endpoints

Why: the project spec allows users to upload files or point DocuMind at documentation URLs. This first version fetches a single page, stores the fetched source through the storage provider, extracts readable text, and indexes it through the same ingestion pipeline as uploads.

We intentionally did not build a full crawler yet. Crawling entire sites needs extra product and safety decisions: URL allowlists, robots policy, page limits, deduplication, rate limits, and retry behavior. A single-page URL ingestion path gives us the right architecture without pretending crawling is solved.

Interview version:

> I added URL ingestion as a controlled first step rather than jumping straight to crawling. The backend fetches one HTTP/HTTPS page, strips HTML into readable text, stores the fetched source, and sends it through the same chunk/embed/store pipeline as uploaded files. A crawler can be layered on later with rate limits, deduplication, and robots-policy handling.

## Step 16: Retrieval Reranking

We added:

- `backend/app/reranking.py`
- `Reranker` protocol
- `NoOpReranker`
- deterministic `LocalLexicalReranker`
- reranker config in answer cache keys
- larger pgvector candidate pools before final top-k
- production readiness check for `RERANKER_PROVIDER=cross-encoder`

Why: vector similarity is a good first-stage retriever, but it is not always the best final ordering. Production RAG commonly retrieves a wider candidate set, then reranks those candidates with a more precise relevance model. That gives the generator better context without changing the public API.

The local reranker is deterministic so tests and demos stay stable. The production gate still expects a cross-encoder because the project spec calls for reranking, and a real cross-encoder is the resume-grade version of this feature.

Interview version:

> I made retrieval two-stage. pgvector retrieves a broader candidate pool, then a reranker chooses the final top-k. Locally, I use a deterministic lexical reranker for stable tests. The provider boundary lets me switch to a cross-encoder reranker in production without changing query, answer, or eval routes.

## Step 17: Answer-Quality Evaluation

We added:

- `backend/app/answer_evaluation.py`
- optional `expected_answer` on eval cases
- per-case `faithfulness` and `answer_relevance`
- per-config mean faithfulness and mean answer relevance
- generated answers included in eval case results
- frontend metric cards and case-table columns for answer quality
- release-readiness check for `EVALUATION_PROVIDER=ragas`
- `AnswerQualityEvaluator` provider boundary
- `RagasAnswerQualityEvaluator` using RAGAS `Faithfulness` and `AnswerRelevancy`
- RAGAS model settings for Gemini evaluator LLM and embeddings

Why: retrieval metrics tell us whether the right evidence reached the generator. They do not tell us whether the generated answer stayed grounded in that evidence or answered the user’s question. Answer-quality eval closes that gap.

The local evaluator is deterministic. Faithfulness checks whether generated answer claims are supported by retrieved context. Answer relevance checks whether the response addresses the question and expected terms. This gives demos and tests stable scores without API credentials.

For production, we added a real RAGAS provider path behind the same interface. RAGAS defines faithfulness as factual consistency between response and retrieved context, and answer relevancy as alignment between response and user input. The provider uses Gemini by default so we can reuse the same API key family as generation and embeddings:

```bash
EVALUATION_PROVIDER=ragas
GEMINI_API_KEY=your_google_ai_studio_key
RAGAS_LLM_MODEL=gemini-2.0-flash
RAGAS_EMBEDDING_MODEL=gemini-embedding-001
```

The readiness gate still fails local mode because deterministic token heuristics are useful for development but too weak to call production evaluation. In production we want evaluator LLM/embedding scoring, and the provider boundary lets us switch without changing the eval route or dashboard.

Interview version:

> I extended eval from retrieval-only to retrieval plus answer quality. Retrieval metrics show whether the right context was found; faithfulness checks whether the answer is supported by that context; answer relevance checks whether the answer addresses the question. Locally I use deterministic heuristics for stable tests, but production can switch `EVALUATION_PROVIDER` to RAGAS, using Gemini as the evaluator LLM and embedding model through the same interface.

## Step 18: Lean Backend Image

We added:

- `backend/requirements.txt` for base API/local dependencies
- `backend/requirements-ml.txt` for optional RAGAS and cross-encoder dependencies
- `INSTALL_ML_DEPS` Docker build arg
- Compose build args for API and worker

Why: production deployment on small EC2 instances should not pull heavy ML dependencies unless the runtime actually needs them. The first RAGAS/cross-encoder build proved that `sentence-transformers` pulls a very large Torch/CUDA dependency tree. That affects image build time, disk use, deploy speed, and EC2 sizing.

Local development uses:

```bash
INSTALL_ML_DEPS=false
docker compose up --build
```

Production evaluator/reranker mode uses:

```bash
INSTALL_ML_DEPS=true docker compose build api worker
docker compose up -d api worker
```

Interview version:

> I split base API dependencies from optional ML dependencies after verifying the image got very large with cross-encoder packages. The API can run local deterministic providers from a lean image, while production can opt into ML dependencies explicitly. That keeps deployment practical and makes resource tradeoffs visible instead of hidden in `requirements.txt`.

## Step 19: Production Env Checklist

We added:

- `.env.production.example`
- `docs/production-checklist.md`
- placeholder-secret rejection in `/release/readiness`

Why: production deployment fails most often because secrets and environment values are scattered. The app already had a release-readiness gate, but it treated any non-empty value as configured. That is dangerous because template values like `replace_me` can look present while still being unusable.

The production template lists exactly where real values go:

- Neon `DATABASE_URL`
- Upstash Redis URLs
- Cloudflare R2 endpoint, access key, secret key, bucket
- Gemini API key
- production CORS origin
- frontend API base URL
- `INSTALL_ML_DEPS=true` when using RAGAS/cross-encoder

The readiness gate now rejects placeholder secrets so a copied template cannot pass as production-ready.

Interview version:

> I created a production env template and checklist so deployment is repeatable instead of tribal knowledge. I also hardened the readiness gate to reject placeholder secrets. That matters because production checks should prove real configuration, not merely non-empty strings.

## Step 20: Production Compose and EC2 Deploy Skeleton

We added:

- multi-stage `frontend/Dockerfile`
- `frontend/nginx.conf` for serving built React assets
- `docker-compose.prod.yml`
- `nginx/nginx.prod.conf`
- `.github/workflows/deploy-ec2.yml`

Why: local Compose is optimized for development: mounted source code, Vite dev server, local Postgres, local Redis, and reload mode. Production should not run that shape. Production Compose now runs API, worker, static frontend, and Nginx only. Persistence moves to managed services through env vars.

The frontend image now has separate development and production targets. Development still runs Vite. Production builds static assets and serves them through Nginx. The root Nginx container routes `/api/*` to FastAPI and everything else to the frontend.

GitHub Actions deploy is intentionally small: SSH into EC2, pull latest `main`, rebuild production Compose, start containers, then smoke-test `/api/health` and `/api/release/readiness`. Service secrets stay in `.env` on EC2, not in GitHub Actions.

Interview version:

> I separated dev Compose from production Compose. Local uses hot reload and local services. Production runs static frontend, API, worker, and Nginx, while Neon, Upstash, and R2 provide managed persistence. I also added a deploy workflow that updates EC2 over SSH and verifies health/readiness after restart.

## Step 21: EC2 Provisioning Runbook

We added:

- `docs/ec2-provisioning.md`
- EC2 setup link in production checklist

Why: deployment needs a repeatable infrastructure path, not vague “launch EC2” advice. The runbook captures billing guardrails, instance size, security-group rules, Docker/Compose/Nginx/Certbot install commands, first deploy commands, DNS/HTTPS steps, and GitHub deploy secrets.

The security rule is explicit: only ports 22, 80, and 443 are public. API port 8000, Vite port 5173, Postgres, and Redis stay private. Public traffic goes through Nginx, which is the correct edge for TLS and routing.

Interview version:

> I wrote an EC2 provisioning runbook so deployment is reproducible. It includes billing alert setup, security group rules, Docker Compose install, production env setup, HTTPS, and GitHub deploy secrets. I deliberately expose only Nginx publicly and keep API/database/cache ports private.

## Step 22: Deployment Safety Checks

We added:

- production Compose healthchecks for API, worker, frontend, and Nginx
- healthy-service dependency between Nginx and upstream app containers
- deploy workflow readiness assertion for `deployable:true`

Why: a container being started is not the same as a service being usable. Healthchecks make Docker report service health, and the deploy workflow now fails if the release-readiness endpoint is not production-ready.

This prevents a weak deployment story where CI/CD says “success” while the app is still running local providers, missing R2, or using localhost CORS.

Interview version:

> I made deployment verification explicit. Production Compose has healthchecks, and the deploy workflow fails unless `/api/release/readiness` returns `deployable:true`. That means a deploy is not considered successful until both runtime health and production configuration are proven.

## Step 23: Managed-Service Setup Guide

We added:

- `docs/managed-services.md`
- `backend/app/release_cli.py`
- release CLI tests

Why: the production checklist says what values are needed, but managed services need a setup order. We now document the order: Neon, Upstash, R2, Gemini, reranker, domain. That order reduces debugging noise because database, cache/queue, object storage, model providers, and domain are validated one layer at a time.

The release CLI lets us validate an env file before or during deployment:

```bash
python -m app.release_cli --env-file .env
```

It exits `0` only when release readiness is deployable. That makes it usable in scripts and SSH sessions, not only through the HTTP API.

Interview version:

> I added a managed-services setup guide and CLI readiness validator. The setup order is deliberate: database first, Redis second, object storage third, model providers fourth, reranker last. The CLI gives the same release-readiness signal without needing to hit the HTTP API, so deployment scripts can fail fast on bad env config.

## Step 24: Database Schema CLI

We added:

- `backend/app/db_cli.py`
- DB CLI tests
- Neon setup docs that run schema initialization explicitly

Why: local app routes can lazily call `ensure_schema`, but production should have an explicit database initialization step. Neon needs the `vector` extension, documents table, chunks table, and indexes before ingestion is trusted.

Command:

```bash
python -m app.db_cli ensure-schema --env-file .env
```

Interview version:

> I added an explicit database schema command for production. Local routes can initialize schema lazily, but production deployment should run schema setup intentionally before traffic. That makes Neon setup repeatable and separates infrastructure initialization from request handling.
