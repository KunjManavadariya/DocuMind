# Render Deployment Runbook

DocuMind now has two operating modes:

- Local managed mode for development and async worker demos.
- Render demo mode for public portfolio access.

The hosted demo is intentionally split by runtime type:

- Frontend: Render Static Site at `https://documind-rag-workbench.onrender.com`
- Backend: Render Docker Web Service at `https://documind-rag-api.onrender.com`
- Worker: local Celery worker when async ingestion is needed
- Database: Neon Postgres with pgvector
- Redis: Upstash Redis
- Source file storage: Cloudflare R2
- Models: Gemini

## Why This Deployment Shape

### Frontend As Static Site

The frontend is a Vite React single-page app. After `npm run build`, it becomes static HTML, CSS, and JavaScript. A static site is the correct deployment type because:

- no Node server is needed after build
- Render can serve files from CDN-like static hosting
- no frontend container needs to stay warm
- no web-service cold start for the UI shell
- frontend deploys are simpler and cheaper

The only frontend production config needed is:

```env
VITE_API_BASE_URL=https://documind-rag-api.onrender.com
```

Vite reads this during build and bakes it into the generated JavaScript bundle.

### Backend As Docker Web Service

The backend is a Python FastAPI app with binary/database/model dependencies. Docker is the right deployment type because:

- runtime is reproducible
- Python version is pinned through `python:3.12-slim`
- dependency install is controlled by `backend/requirements.txt`
- Render only needs to build and run the container
- backend can use Render-provided `PORT`

Backend Docker command:

```dockerfile
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
```

Render sets `PORT`; local Docker fallback stays `8000`.

### Worker Kept Local

The Celery worker is not hosted on Render in the current free demo setup. Sync ingestion, URL ingestion, retrieval, answer generation, and eval work through the hosted frontend/backend. Async ingestion only completes when local worker runs with the same `.env`.

Why:

- async worker is useful for showing background processing
- free hosted worker capacity can be limited/unreliable
- project does not require always-on async processing
- keeping worker local avoids unnecessary always-on compute

## Current Public URLs

Use these links in GitHub and LinkedIn:

```text
Frontend: https://documind-rag-workbench.onrender.com
Backend:  https://documind-rag-api.onrender.com
```

Health checks:

```bash
curl https://documind-rag-api.onrender.com/health
curl https://documind-rag-api.onrender.com/ready
```

Expected:

```json
{"status":"ok","service":"documind-api","environment":"render-free"}
```

```json
{"status":"ready","database":"ok","redis":"ok"}
```

## Render Services

### `documind-rag-workbench`

Type: Static Site

Settings:

```text
Repository: https://github.com/KunjManavadariya/DocuMind
Branch: main
Root directory: frontend
Build command: npm ci && npm run build
Publish directory: dist
Environment:
  VITE_API_BASE_URL=https://documind-rag-api.onrender.com
```

Why root directory is `frontend`: the Vite app has its own `package.json`, `package-lock.json`, and source tree.

Why publish directory is `dist`: Vite writes production assets there.

### `documind-rag-api`

Type: Web Service

Settings:

```text
Repository: https://github.com/KunjManavadariya/DocuMind
Branch: main
Root directory: backend
Runtime: Docker
Dockerfile: backend/Dockerfile
Plan: free
Health check path: /health
```

Important env:

```env
APP_ENV=render-free
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
CORS_ORIGIN_REGEX=https://.*\.onrender\.com
INSTALL_ML_DEPS=false
DATABASE_URL=...
REDIS_URL=...
CELERY_BROKER_URL=...
CELERY_RESULT_BACKEND=...
DOCUMENT_STORAGE_PROVIDER=r2
CLOUDFLARE_R2_ENDPOINT_URL=...
CLOUDFLARE_R2_ACCESS_KEY_ID=...
CLOUDFLARE_R2_SECRET_ACCESS_KEY=...
CLOUDFLARE_R2_BUCKET=...
GENERATION_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
EVALUATION_PROVIDER=local
RERANKER_PROVIDER=local
GEMINI_API_KEY=...
GEMINI_GENERATION_MODEL=gemini-2.5-flash-lite
GEMINI_EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=384
```

Why CORS regex exists: frontend Render URLs can change during deployment experiments. Regex allows trusted Render-hosted DocuMind frontends without hardcoding a single origin. Localhost origins stay listed for local dev.

## Deploy Helper

The script below creates both Render services from local `.env`:

```bash
scripts/render-create-services.sh
```

It reads secrets from `.env` and sends them to Render environment variables. It does not print secret values.

Use custom names only when needed:

```bash
API_NAME=documind-rag-api WEB_NAME=documind-rag-workbench scripts/render-create-services.sh
```

## Verify Hosted Demo

### 1. Frontend

```bash
curl -I https://documind-rag-workbench.onrender.com/
```

Expected:

```text
HTTP/2 200
```

### 2. Backend Liveness

```bash
curl https://documind-rag-api.onrender.com/health
```

This proves FastAPI is running.

### 3. Backend Readiness

```bash
curl https://documind-rag-api.onrender.com/ready
```

This proves FastAPI can reach Neon and Upstash.

### 4. CORS

```bash
curl -I \
  -H "Origin: https://documind-rag-workbench.onrender.com" \
  https://documind-rag-api.onrender.com/health
```

Look for:

```text
access-control-allow-origin: https://documind-rag-workbench.onrender.com
```

### 5. Answer Path

```bash
curl -X POST https://documind-rag-api.onrender.com/query/answer \
  -H "Content-Type: application/json" \
  -H "Origin: https://documind-rag-workbench.onrender.com" \
  -d '{"question":"What database does DocuMind use for semantic search?","top_k":3}'
```

Expected answer should mention Neon Postgres with pgvector when the smoke corpus exists.

## Hosted Demo Workflow

1. Open `https://documind-rag-workbench.onrender.com`.
2. Confirm top API URL is `https://documind-rag-api.onrender.com`.
3. Upload a small `.txt`, `.md`, `.markdown`, or searchable `.pdf`.
4. Keep `Async` off for hosted-only demo.
5. Click `Ingest`.
6. Ask a question from the uploaded file.
7. Inspect citations and retrieved source chunks.
8. Open Eval tab.
9. Run eval cases.

Use `Async` only when local worker is running.

## Async Worker For Hosted Backend

To process async jobs created by hosted backend, run local worker with same `.env` values:

```bash
docker compose -f docker-compose.managed-local.yml up worker
```

The worker connects to same Upstash broker/result backend, same Neon database, same R2 bucket, and same Gemini key. That means hosted API can enqueue a job and local worker can process it.

## Troubleshooting

### Static Site Loads But API Shows Offline

Check:

```bash
curl https://documind-rag-api.onrender.com/health
```

Likely causes:

- backend sleeping on Render free tier
- backend deploy failed
- frontend build has wrong `VITE_API_BASE_URL`
- CORS origin mismatch

### `/ready` Fails

Likely causes:

- Neon suspended or URL wrong
- Upstash URL wrong
- Redis TLS URL missing `rediss://`
- secret not copied to Render

### Upload Fails

Likely causes:

- R2 credentials wrong
- bucket name wrong
- file type unsupported
- Gemini embedding call failed
- Neon schema missing

### Async Job Stays Queued

Expected if local worker is not running. Start worker locally or use sync ingestion.

### First Request Is Slow

Render free web services can cold-start after inactivity. Static frontend should load quickly; backend can take longer on first API call.

