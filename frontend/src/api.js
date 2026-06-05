const API_BASE_URL_STORAGE_KEY = "documind.apiBaseUrl";
const runtimeApiBaseUrl = window.__DOCUMIND_API_BASE_URL__;
const DEFAULT_API_BASE_URL =
  runtimeApiBaseUrl || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function normalizeApiBaseUrl(value) {
  return value.trim().replace(/\/+$/, "");
}

export function getApiBaseUrl() {
  const stored = window.localStorage.getItem(API_BASE_URL_STORAGE_KEY);
  return normalizeApiBaseUrl(stored || DEFAULT_API_BASE_URL);
}

export function setApiBaseUrl(value) {
  const normalized = normalizeApiBaseUrl(value);
  if (!normalized) {
    window.localStorage.removeItem(API_BASE_URL_STORAGE_KEY);
    return getApiBaseUrl();
  }

  window.localStorage.setItem(API_BASE_URL_STORAGE_KEY, normalized);
  return normalized;
}

async function request(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, options);
  const contentType = response.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const detail = typeof body === "object" && body !== null ? body.detail : body;
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return body;
}

export function getHealth() {
  return request("/health");
}

export function getDocuments() {
  return request("/documents");
}

export function clearCorpus() {
  return request("/documents", {
    method: "DELETE",
  });
}

export function uploadDocument({ file, chunkSize, chunkOverlap, asyncMode }) {
  const formData = new FormData();
  formData.append("file", file);

  const endpoint = asyncMode ? "/documents/upload-async" : "/documents/upload";
  const params = new URLSearchParams({
    chunk_size: String(chunkSize),
    chunk_overlap: String(chunkOverlap),
  });

  return request(`${endpoint}?${params.toString()}`, {
    method: "POST",
    body: formData,
  });
}

export function ingestUrl({ url, chunkSize, chunkOverlap, asyncMode }) {
  const endpoint = asyncMode ? "/documents/ingest-url-async" : "/documents/ingest-url";

  return request(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      url,
      chunk_size: chunkSize,
      chunk_overlap: chunkOverlap,
    }),
  });
}

export function getJobStatus(taskId) {
  return request(`/documents/jobs/${taskId}`);
}

export function askQuestion({ question, topK, documentIds = [] }) {
  return request("/query/answer", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      top_k: topK,
      document_ids: documentIds,
    }),
  });
}

export function runEvaluation({ cases, configs, documentIds = [] }) {
  return request("/eval/run", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      cases,
      configs,
      document_ids: documentIds,
    }),
  });
}
