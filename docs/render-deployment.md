# Render Deployment Runbook

This path deploys DocuMind on Render Free where available:

- `documind-api`: FastAPI Docker web service.
- `documind-web`: React static site.
- `documind-worker`: Celery Docker background worker.

Render Free is resource-constrained, so this config keeps heavy optional ML off:

```env
INSTALL_ML_DEPS=false
RERANKER_PROVIDER=local
EVALUATION_PROVIDER=local
```

Gemini still handles production generation and embeddings. RAGAS and cross-encoder reranking can be enabled later on a larger plan.

## 1. Push Code To GitHub

Create a GitHub repo and push this project. Do not commit `.env`.

Required committed file:

```text
render.yaml
```

## 2. Create Blueprint

Render Dashboard:

1. New → Blueprint.
2. Connect GitHub repo.
3. Select repo containing `render.yaml`.
4. Render detects:
   - `documind-api`
   - `documind-web`
   - `documind-worker`
5. Create resources.

If Render rejects `plan: free` for `documind-worker`, create the worker manually from dashboard with the same Docker settings and env values.

## 3. Fill Secrets

Set these on both `documind-api` and `documind-worker`:

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

Use same `REDIS_URL` for all three Redis/Celery URLs if using one Upstash database:

```env
REDIS_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_BROKER_URL=rediss://default:TOKEN@HOST:PORT/0
CELERY_RESULT_BACKEND=rediss://default:TOKEN@HOST:PORT/0
```

Do not paste secrets into chat. Fill them in Render dashboard.

## 4. Update CORS If Service Names Change

Default frontend URL in `render.yaml`:

```env
CORS_ORIGINS=https://documind-web.onrender.com,http://localhost:5173,http://127.0.0.1:5173
```

If Render creates a different frontend URL, update `CORS_ORIGINS` on `documind-api`.

## 5. Initialize Database

Render has no one-shot command in Blueprint. Use local machine after secrets are ready:

```bash
cd backend
DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require" python -m app.db_cli ensure-schema
```

Alternative: use Render API service Shell if available:

```bash
python -m app.db_cli ensure-schema
```

## 6. Verify

Open:

```text
https://documind-api.onrender.com/health
https://documind-api.onrender.com/ready
https://documind-api.onrender.com/release/readiness
```

For Render Free, `/release/readiness` may be `deployable:false` because release gate expects full production mode. Demo can still work when:

```text
/health = ok
/ready = ready
upload works
async upload works
ask works
eval works
```

## 7. Frontend API URL

Open frontend:

```text
https://documind-web.onrender.com
```

If API URL differs, paste actual API URL into top-right API field and save:

```text
https://documind-api.onrender.com
```

The frontend stores this in browser local storage, so no rebuild is needed.

## Interview Explanation

I deployed DocuMind to Render as three services because Render maps one long-running process per service: web API, static frontend, and background worker. Free Render cannot comfortably run heavy local ML, so the free demo uses Gemini for generation and embeddings, local reranking, and local eval scoring. The architecture remains production-shaped: Postgres/pgvector, Redis/Celery, R2 storage, provider boundaries, and async ingestion are still exercised.
