# Production Checklist

Use this when moving DocuMind from local MVP to real deployment.

## 1. Accounts

Detailed EC2 setup: `docs/ec2-provisioning.md`.
Managed service setup: `docs/managed-services.md`.

- AWS account created.
- Billing alert set to 1 USD.
- EC2 instance created.
- Security group allows SSH, HTTP, HTTPS.
- Neon project created.
- Upstash Redis database or databases created.
- Cloudflare R2 bucket created.
- Gemini API key created.
- Domain selected and DNS editable.

## 2. Secrets

Never commit real secrets. Put production values only in `.env` on EC2.

Copy template:

```bash
cp .env.production.example .env
```

Fill:

- `DATABASE_URL` from Neon.
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` from Upstash.
- `CLOUDFLARE_R2_ENDPOINT_URL`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`
- `GEMINI_API_KEY`
- `CORS_ORIGINS`
- `VITE_API_BASE_URL`

## 3. Build Mode

Lean local build:

```bash
INSTALL_ML_DEPS=false docker compose build api worker
```

Production RAGAS/cross-encoder build:

```bash
INSTALL_ML_DEPS=true docker compose build api worker
```

Why: `ragas` and `sentence-transformers` pull heavy ML dependencies. Production should opt in deliberately.

## 4. Release Readiness

Run:

```bash
curl http://localhost:8000/release/readiness
```

Or validate an env file before deploy:

```bash
docker compose exec -T api python -m app.release_cli --env-file .env
```

Required result before public launch:

```json
{"deployable": true}
```

If `deployable` is false, fix each failed check before calling deployment complete.

## 5. EC2 Deploy Flow

On EC2:

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx
git clone <repo-url> DocuMind
cd DocuMind
cp .env.production.example .env
```

Fill `.env`, then:

```bash
INSTALL_ML_DEPS=true docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
docker compose -f docker-compose.prod.yml up -d
```

Verify:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
curl http://localhost/api/release/readiness
```

All production containers should become `healthy`. If readiness returns `deployable:false`, do not treat deployment as complete.

## 6. HTTPS

After DNS points to EC2:

```bash
sudo certbot --nginx -d your-domain.com
```

Then update:

```env
CORS_ORIGINS=https://your-domain.com
VITE_API_BASE_URL=https://your-domain.com
```

Restart:

```bash
docker compose -f docker-compose.prod.yml up -d
```

## 7. GitHub Actions Deploy

Add repository secrets:

- `EC2_HOST`: EC2 public IP or domain.
- `EC2_USER`: SSH user, usually `ubuntu`.
- `EC2_SSH_KEY`: private SSH key that can access EC2.
- `EC2_APP_DIR`: repo path on EC2, for example `/home/ubuntu/DocuMind`.

Workflow:

- `.github/workflows/ci.yml` runs tests/build.
- `.github/workflows/deploy-ec2.yml` deploys `main` to EC2.
- Deploy workflow pulls latest `main`, rebuilds production compose, starts containers, checks `/api/health`, then fails unless `/api/release/readiness` returns `deployable:true`.

Do not put service credentials in GitHub Actions. Keep Neon, Upstash, R2, and Gemini values in `.env` on EC2.

## 8. Interview Explanation

I separated local runtime from production runtime. Local mode uses deterministic providers and a lean image so tests and demos are stable. Production mode switches providers through environment variables: Neon for pgvector, Upstash for Redis/Celery, Cloudflare R2 for source files, Gemini for generation/embeddings, RAGAS for answer-quality evaluation, and cross-encoder reranking. Production Compose runs only app containers because persistence is managed externally. `/release/readiness` converts those architecture decisions into an executable checklist.
