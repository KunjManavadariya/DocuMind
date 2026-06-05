#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
RENDER_BIN="${RENDER_BIN:-/opt/homebrew/bin/render}"
REPO_URL="${REPO_URL:-https://github.com/KunjManavadariya/DocuMind}"
BRANCH="${BRANCH:-main}"
API_NAME="${API_NAME:-documind-api-kunj}"
WEB_NAME="${WEB_NAME:-documind-web-kunj}"
API_URL="https://${API_NAME}.onrender.com"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo ".env missing at ${ENV_FILE}" >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env: ${name}" >&2
    exit 1
  fi
}

required=(
  DATABASE_URL
  REDIS_URL
  CELERY_BROKER_URL
  CELERY_RESULT_BACKEND
  CLOUDFLARE_R2_ENDPOINT_URL
  CLOUDFLARE_R2_ACCESS_KEY_ID
  CLOUDFLARE_R2_SECRET_ACCESS_KEY
  CLOUDFLARE_R2_BUCKET
  GEMINI_API_KEY
)

for name in "${required[@]}"; do
  require_env "${name}"
done

"${RENDER_BIN}" services create \
  --name "${API_NAME}" \
  --type web_service \
  --repo "${REPO_URL}" \
  --branch "${BRANCH}" \
  --runtime docker \
  --root-directory backend \
  --plan free \
  --health-check-path /health \
  --env-var APP_ENV=render-free \
  --env-var CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173 \
  --env-var 'CORS_ORIGIN_REGEX=https://.*\.onrender\.com' \
  --env-var INSTALL_ML_DEPS="${INSTALL_ML_DEPS:-false}" \
  --env-var DATABASE_URL="${DATABASE_URL}" \
  --env-var REDIS_URL="${REDIS_URL}" \
  --env-var CELERY_BROKER_URL="${CELERY_BROKER_URL}" \
  --env-var CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND}" \
  --env-var CACHE_ENABLED="${CACHE_ENABLED:-true}" \
  --env-var EMBEDDING_CACHE_TTL_SECONDS="${EMBEDDING_CACHE_TTL_SECONDS:-86400}" \
  --env-var ANSWER_CACHE_TTL_SECONDS="${ANSWER_CACHE_TTL_SECONDS:-600}" \
  --env-var DOCUMENT_STORAGE_PROVIDER="${DOCUMENT_STORAGE_PROVIDER:-r2}" \
  --env-var CLOUDFLARE_R2_ENDPOINT_URL="${CLOUDFLARE_R2_ENDPOINT_URL}" \
  --env-var CLOUDFLARE_R2_ACCESS_KEY_ID="${CLOUDFLARE_R2_ACCESS_KEY_ID}" \
  --env-var CLOUDFLARE_R2_SECRET_ACCESS_KEY="${CLOUDFLARE_R2_SECRET_ACCESS_KEY}" \
  --env-var CLOUDFLARE_R2_BUCKET="${CLOUDFLARE_R2_BUCKET}" \
  --env-var URL_FETCH_TIMEOUT_SECONDS="${URL_FETCH_TIMEOUT_SECONDS:-10}" \
  --env-var URL_FETCH_MAX_BYTES="${URL_FETCH_MAX_BYTES:-2000000}" \
  --env-var LLM_PROVIDER="${LLM_PROVIDER:-gemini}" \
  --env-var GENERATION_PROVIDER="${GENERATION_PROVIDER:-gemini}" \
  --env-var EMBEDDING_PROVIDER="${EMBEDDING_PROVIDER:-gemini}" \
  --env-var EVALUATION_PROVIDER="${EVALUATION_PROVIDER:-local}" \
  --env-var GEMINI_API_KEY="${GEMINI_API_KEY}" \
  --env-var GEMINI_GENERATION_MODEL="${GEMINI_GENERATION_MODEL:-gemini-2.5-flash-lite}" \
  --env-var GEMINI_EMBEDDING_MODEL="${GEMINI_EMBEDDING_MODEL:-gemini-embedding-001}" \
  --env-var GEMINI_TEMPERATURE="${GEMINI_TEMPERATURE:-0.2}" \
  --env-var EMBEDDING_DIMENSION="${EMBEDDING_DIMENSION:-384}" \
  --env-var RERANKER_PROVIDER="${RERANKER_PROVIDER:-local}" \
  --env-var RERANKER_CANDIDATE_MULTIPLIER="${RERANKER_CANDIDATE_MULTIPLIER:-4}" \
  --env-var RERANKER_MODEL="${RERANKER_MODEL:-cross-encoder/ms-marco-MiniLM-L-6-v2}" \
  --env-var RAGAS_LLM_MODEL="${RAGAS_LLM_MODEL:-gemini-2.0-flash}" \
  --env-var RAGAS_EMBEDDING_MODEL="${RAGAS_EMBEDDING_MODEL:-gemini-embedding-001}" \
  --confirm

"${RENDER_BIN}" services create \
  --name "${WEB_NAME}" \
  --type web_service \
  --repo "${REPO_URL}" \
  --branch "${BRANCH}" \
  --runtime docker \
  --root-directory frontend \
  --plan free \
  --env-var VITE_API_BASE_URL="${API_URL}" \
  --confirm

echo "API: ${API_URL}"
echo "Web: https://${WEB_NAME}.onrender.com"
