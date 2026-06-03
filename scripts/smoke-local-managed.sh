#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://127.0.0.1:8000}"
QUESTION="Which managed services does local DocuMind use?"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing command: $1" >&2
    exit 1
  fi
}

json_field() {
  python3 -c "import json,sys; data=json.load(sys.stdin); print($1)"
}

curl_retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if curl -fsS "$@"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

require_command curl
require_command python3

echo "1. health"
curl_retry "$API_BASE_URL/health" >/dev/null

echo "2. readiness"
curl_retry "$API_BASE_URL/ready" >/dev/null

echo "3. ingest smoke document"
INGEST_RESPONSE="$(
  curl_retry -X POST "$API_BASE_URL/documents/ingest-text" \
    -H "Content-Type: application/json" \
    -d '{
      "title": "DocuMind Local Managed Smoke",
      "content": "DocuMind local managed mode runs FastAPI, React, and Celery locally while using Neon, Upstash, Cloudflare R2, and Gemini as managed services.",
      "chunk_size": 80,
      "chunk_overlap": 10
    }'
)"
DOCUMENT_ID="$(printf '%s' "$INGEST_RESPONSE" | json_field 'data["document_id"]')"

if [[ -z "$DOCUMENT_ID" ]]; then
  echo "missing document_id in ingest response" >&2
  exit 1
fi

echo "4. retrieve scoped context"
RETRIEVE_RESPONSE="$(
  curl_retry -X POST "$API_BASE_URL/query/retrieve" \
    -H "Content-Type: application/json" \
    -d "{
      \"question\": \"$QUESTION\",
      \"top_k\": 3,
      \"document_ids\": [\"$DOCUMENT_ID\"]
    }"
)"
RETRIEVED_COUNT="$(printf '%s' "$RETRIEVE_RESPONSE" | json_field 'len(data["results"])')"

if [[ "$RETRIEVED_COUNT" -lt 1 ]]; then
  echo "retrieval returned no chunks" >&2
  exit 1
fi

echo "5. generate cited answer"
ANSWER_RESPONSE="$(
  curl_retry -X POST "$API_BASE_URL/query/answer" \
    -H "Content-Type: application/json" \
    -d "{
      \"question\": \"$QUESTION\",
      \"top_k\": 3,
      \"document_ids\": [\"$DOCUMENT_ID\"]
    }"
)"
CITATION_COUNT="$(printf '%s' "$ANSWER_RESPONSE" | json_field 'len(data["citations"])')"

if [[ "$CITATION_COUNT" -lt 1 ]]; then
  echo "answer returned no citations" >&2
  exit 1
fi

echo "6. run eval smoke"
curl_retry -X POST "$API_BASE_URL/eval/run" \
  -H "Content-Type: application/json" \
  -d "{
    \"document_ids\": [\"$DOCUMENT_ID\"],
    \"cases\": [
      {
        \"id\": \"local-managed-services\",
        \"question\": \"$QUESTION\",
        \"expected_terms\": [\"Neon\", \"Upstash\", \"Cloudflare R2\", \"Gemini\"],
        \"expected_answer\": \"DocuMind uses Neon, Upstash, Cloudflare R2, and Gemini as managed services.\"
      }
    ],
    \"configs\": [
      {\"name\": \"top-1\", \"top_k\": 1}
    ]
  }" >/dev/null

echo "smoke ok: $DOCUMENT_ID"
