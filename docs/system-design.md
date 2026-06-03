# DocuMind System Design

DocuMind is local-first by final decision. Frontend, API, and worker run on the laptop through Docker Compose. Persistence and model providers are managed services.

## Runtime

- React frontend: browser UI on `localhost:5173`
- FastAPI API: request layer on `localhost:8000`
- Celery worker: background ingestion process
- Neon Postgres with pgvector: documents, chunks, embeddings, vector search
- Upstash Redis: JSON cache, Celery broker, Celery result backend
- Cloudflare R2: original source document storage
- Gemini: answer generation and embeddings

## Data Flow

1. User uploads a file or enters a URL.
2. API extracts text.
3. API stores original source file in R2.
4. Ingestion chunks text with overlap.
5. Embedding provider embeds each chunk.
6. Neon stores document metadata, chunk text, token counts, and pgvector embeddings.
7. User asks a question.
8. Backend embeds question.
9. pgvector retrieves similar chunks.
10. Reranker reorders candidates.
11. Gemini generates answer from retrieved context.
12. UI shows answer, citations, source chunks, and scores.

## Why This Shape

FastAPI stays stateless. Celery isolates slow ingestion from request handling. Neon keeps vector search close to document metadata. R2 keeps large source files out of Postgres. Redis avoids repeated model calls and powers async jobs. Provider interfaces keep Gemini, local eval, and optional heavy ML replaceable without route rewrites.

## Evaluation

Eval runs use same retrieval and answer path as user questions. Each case has a question plus expected terms or source. Dashboard compares `top-1`, `top-3`, and `top-5` using recall, MRR, context precision, faithfulness, and answer relevance.

## Explanation

DocuMind is not a prompt demo. It is a small RAG system with visible ingestion, retrieval, generation, cache, async worker, corpus scoping, and eval loops. Local runtime keeps demo cost low, while managed backing services preserve real architecture boundaries.
