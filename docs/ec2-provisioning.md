# EC2 Provisioning Runbook

Use this before filling production credentials.

## 1. AWS Guardrails

Create billing alert first.

- AWS Billing → Budgets.
- Create cost budget.
- Amount: `1 USD`.
- Alert email: your email.

Why: a portfolio deploy should prove production maturity without accidental spend.

## 2. Instance

Recommended starter instance:

- AMI: Ubuntu Server LTS.
- Type: `t2.micro` or `t3.micro` if free tier eligible in your account.
- Storage: at least 20 GB gp3.
- Key pair: create or use existing SSH key.
- Security group:
  - SSH `22` from your IP only.
  - HTTP `80` from `0.0.0.0/0`.
  - HTTPS `443` from `0.0.0.0/0`.

Do not expose `8000`, `5173`, `5432`, or `6379` publicly. Nginx is public edge. API, frontend, and worker stay behind Docker network.

## 3. First SSH

From local machine:

```bash
ssh -i /path/to/key.pem ubuntu@EC2_PUBLIC_IP
```

Update packages:

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

Install runtime:

```bash
sudo apt-get install -y docker.io docker-compose-plugin nginx certbot python3-certbot-nginx git
sudo usermod -aG docker ubuntu
```

Log out and SSH back in so Docker group applies.

Verify:

```bash
docker --version
docker compose version
nginx -v
```

## 4. Clone App

```bash
git clone <repo-url> /home/ubuntu/DocuMind
cd /home/ubuntu/DocuMind
cp .env.production.example .env
```

Fill `.env` on EC2 only.

Required real values:

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `CLOUDFLARE_R2_ENDPOINT_URL`
- `CLOUDFLARE_R2_ACCESS_KEY_ID`
- `CLOUDFLARE_R2_SECRET_ACCESS_KEY`
- `CLOUDFLARE_R2_BUCKET`
- `GEMINI_API_KEY`
- `CORS_ORIGINS`
- `VITE_API_BASE_URL`

## 5. First Production Run

```bash
INSTALL_ML_DEPS=true docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm api python -m app.db_cli ensure-schema --env-file .env
docker compose -f docker-compose.prod.yml up -d
```

Verify containers:

```bash
docker compose -f docker-compose.prod.yml ps
curl http://localhost/api/health
curl http://localhost/api/release/readiness
```

Expected final readiness:

```json
{"deployable": true}
```

## 6. Domain and HTTPS

Point DNS:

- `A` record: `your-domain.com` → EC2 public IP.

After DNS resolves:

```bash
sudo certbot --nginx -d your-domain.com
```

Update `.env`:

```env
CORS_ORIGINS=https://your-domain.com
VITE_API_BASE_URL=https://your-domain.com/api
```

Rebuild frontend because `VITE_API_BASE_URL` is compile-time:

```bash
INSTALL_ML_DEPS=true docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d
```

Verify public URL:

```bash
curl https://your-domain.com/api/health
curl https://your-domain.com/api/release/readiness
```

## 7. GitHub Deploy Secrets

In GitHub repo → Settings → Secrets and variables → Actions:

- `EC2_HOST`: EC2 public IP or domain.
- `EC2_USER`: `ubuntu`.
- `EC2_SSH_KEY`: private SSH key.
- `EC2_APP_DIR`: `/home/ubuntu/DocuMind`.

Do not add Neon, Upstash, R2, or Gemini secrets to GitHub Actions. They stay in `.env` on EC2.

## 8. What I Need From You

Tell me when AWS instance exists. Then provide non-secret values first:

- EC2 public IP.
- Domain, if using one.
- Repo URL.
- EC2 app directory if not `/home/ubuntu/DocuMind`.

Do not paste private keys or API keys into chat unless explicitly needed and you are comfortable rotating them later.

## Interview Explanation

I used one EC2 instance for the first public release because it is simple, cheap, and enough to prove production deployment. The important production boundaries still exist: API and worker are stateless containers, vector storage is managed Neon, source files are in R2, Redis/Celery state is in Upstash, and Nginx terminates public traffic. That keeps the first deployment practical while preserving a path to scale horizontally later.
