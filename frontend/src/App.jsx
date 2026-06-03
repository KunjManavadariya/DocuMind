import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  Database,
  FileText,
  Gauge,
  Globe,
  Loader2,
  MessageSquareText,
  Play,
  RotateCw,
  Search,
  Send,
  Server,
  Target,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";
import {
  askQuestion,
  clearCorpus,
  getApiBaseUrl,
  getDocuments,
  getHealth,
  getJobStatus,
  ingestUrl,
  runEvaluation,
  setApiBaseUrl,
  uploadDocument,
} from "./api";
import "./styles.css";

const DEFAULT_CHUNK_SIZE = 256;
const DEFAULT_CHUNK_OVERLAP = 40;
const DEFAULT_EVAL_CASES = [
  {
    id: "semantic-database",
    question: "What database does DocuMind use for semantic search?",
    expected_terms: ["postgres", "pgvector"],
    expected_answer: "DocuMind uses Postgres with pgvector for semantic search.",
  },
  {
    id: "cache-layer",
    question: "What is Redis used for?",
    expected_terms: ["redis", "caching"],
    expected_answer: "Redis is used for caching repeated answers and embeddings.",
  },
  {
    id: "background-ingestion",
    question: "What processes ingestion jobs in the background?",
    expected_terms: ["celery", "background"],
    expected_answer: "Celery processes document ingestion jobs in the background.",
  },
];
const DEFAULT_EVAL_CONFIGS = [
  { name: "top-1", top_k: 1 },
  { name: "top-3", top_k: 3 },
  { name: "top-5", top_k: 5 },
];

function App() {
  const [health, setHealth] = useState({ state: "loading", data: null, error: null });
  const [apiBaseInput, setApiBaseInput] = useState(getApiBaseUrl());
  const [activeView, setActiveView] = useState("ask");
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [asyncMode, setAsyncMode] = useState(false);
  const [uploadState, setUploadState] = useState({ state: "idle", message: "", job: null });
  const [question, setQuestion] = useState("");
  const [answerState, setAnswerState] = useState({ state: "idle", data: null, error: null });
  const [corpusState, setCorpusState] = useState({ state: "loading", documents: [], error: null });
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([]);
  const [evalCasesText, setEvalCasesText] = useState(JSON.stringify(DEFAULT_EVAL_CASES, null, 2));
  const [evalState, setEvalState] = useState({ state: "idle", data: null, error: null });
  const [history, setHistory] = useState([]);
  const pollRef = useRef(null);

  useEffect(() => {
    checkHealth();
    refreshCorpus();

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  const latestSources = answerState.data?.sources ?? [];
  const statusLabel = health.state === "ready" ? "online" : health.state;
  const canAsk = question.trim().length > 0 && answerState.state !== "loading";
  const canUpload = file && uploadState.state !== "loading";
  const canIngestUrl = url.trim().length > 0 && uploadState.state !== "loading";
  const canClearCorpus = corpusState.state !== "loading" && corpusState.documents.length > 0;
  const canRunEval = evalState.state !== "loading";
  const chunkTotal = corpusState.documents.reduce((total, document) => total + document.chunks_created, 0);
  const scopedDocumentIds = selectedDocumentIds.filter((id) =>
    corpusState.documents.some((document) => document.id === id),
  );
  const scopeLabel = scopedDocumentIds.length === 0 ? "All documents" : `${scopedDocumentIds.length} selected`;

  async function checkHealth() {
    try {
      const data = await getHealth();
      setHealth({ state: "ready", data, error: null });
    } catch (error) {
      setHealth({ state: "error", data: null, error: error.message });
    }
  }

  async function handleApiBaseSave(event) {
    event.preventDefault();
    const savedUrl = setApiBaseUrl(apiBaseInput);
    setApiBaseInput(savedUrl);
    setHealth({ state: "loading", data: null, error: null });
    await checkHealth();
    await refreshCorpus();
  }

  async function refreshCorpus() {
    setCorpusState((current) => ({ ...current, state: "loading", error: null }));
    try {
      const data = await getDocuments();
      setCorpusState({ state: "ready", documents: data.documents, error: null });
      setSelectedDocumentIds((ids) =>
        ids.filter((id) => data.documents.some((document) => document.id === id)),
      );
    } catch (error) {
      setCorpusState({ state: "error", documents: [], error: error.message });
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    if (!file) return;

    setUploadState({ state: "loading", message: "Uploading", job: null });
    try {
      const result = await uploadDocument({
        file,
        chunkSize: DEFAULT_CHUNK_SIZE,
        chunkOverlap: DEFAULT_CHUNK_OVERLAP,
        asyncMode,
      });

      if (asyncMode) {
        setUploadState({ state: "queued", message: "Queued", job: result });
        startPolling(result.task_id);
      } else {
        setUploadState({
          state: "ready",
          message: `${result.chunks_created} chunks indexed`,
          job: null,
        });
        refreshCorpus();
      }
    } catch (error) {
      setUploadState({ state: "error", message: error.message, job: null });
    }
  }

  async function handleUrlIngest() {
    if (!canIngestUrl) return;

    setUploadState({ state: "loading", message: "Fetching URL", job: null });
    try {
      const result = await ingestUrl({
        url: url.trim(),
        chunkSize: DEFAULT_CHUNK_SIZE,
        chunkOverlap: DEFAULT_CHUNK_OVERLAP,
        asyncMode,
      });

      if (asyncMode) {
        setUploadState({ state: "queued", message: "Queued", job: result });
        startPolling(result.task_id);
      } else {
        setUploadState({
          state: "ready",
          message: `${result.chunks_created} chunks indexed`,
          job: null,
        });
        setUrl("");
        refreshCorpus();
      }
    } catch (error) {
      setUploadState({ state: "error", message: error.message, job: null });
    }
  }

  function startPolling(taskId) {
    if (pollRef.current) {
      clearInterval(pollRef.current);
    }

    pollRef.current = setInterval(async () => {
      try {
        const status = await getJobStatus(taskId);
        if (status.status === "SUCCESS") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setUploadState({
            state: "ready",
            message: `${status.result.chunks_created} chunks indexed`,
            job: status,
          });
          setUrl("");
          refreshCorpus();
        } else if (status.status === "FAILURE") {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setUploadState({
            state: "error",
            message: status.error ?? "Ingestion failed",
            job: status,
          });
        } else {
          setUploadState({ state: "queued", message: status.status.toLowerCase(), job: status });
        }
      } catch (error) {
        setUploadState({ state: "error", message: error.message, job: null });
      }
    }, 1600);
  }

  async function handleAsk(event) {
    event.preventDefault();
    if (!canAsk) return;

    const submittedQuestion = question.trim();
    setAnswerState({ state: "loading", data: null, error: null });
    try {
      const data = await askQuestion({
        question: submittedQuestion,
        topK: 5,
        documentIds: scopedDocumentIds,
      });
      setAnswerState({ state: "ready", data, error: null });
      setHistory((items) => [data, ...items].slice(0, 5));
      setQuestion("");
    } catch (error) {
      setAnswerState({ state: "error", data: null, error: error.message });
    }
  }

  async function handleRunEval() {
    setEvalState({ state: "loading", data: null, error: null });
    try {
      const cases = JSON.parse(evalCasesText);
      if (!Array.isArray(cases) || cases.length === 0) {
        throw new Error("Eval cases must be a non-empty JSON array.");
      }

      const data = await runEvaluation({
        cases,
        configs: DEFAULT_EVAL_CONFIGS,
        documentIds: scopedDocumentIds,
      });
      setEvalState({ state: "ready", data, error: null });
    } catch (error) {
      setEvalState({ state: "error", data: null, error: error.message });
    }
  }

  async function handleClearCorpus() {
    const confirmed = window.confirm("Clear all indexed documents from this local corpus?");
    if (!confirmed) return;

    setCorpusState((current) => ({ ...current, state: "loading", error: null }));
    try {
      const result = await clearCorpus();
      setCorpusState({ state: "ready", documents: [], error: null });
      setSelectedDocumentIds([]);
      setAnswerState({ state: "idle", data: null, error: null });
      setHistory([]);
      setEvalState({ state: "idle", data: null, error: null });
      setUploadState({
        state: "ready",
        message: `${result.documents_deleted} documents cleared`,
        job: null,
      });
    } catch (error) {
      setCorpusState({ state: "error", documents: [], error: error.message });
    }
  }

  function handleToggleDocument(documentId) {
    setSelectedDocumentIds((ids) =>
      ids.includes(documentId)
        ? ids.filter((id) => id !== documentId)
        : [...ids, documentId],
    );
    setAnswerState({ state: "idle", data: null, error: null });
    setEvalState({ state: "idle", data: null, error: null });
  }

  function handleClearScope() {
    setSelectedDocumentIds([]);
    setAnswerState({ state: "idle", data: null, error: null });
    setEvalState({ state: "idle", data: null, error: null });
  }

  const uploadIcon = useMemo(() => {
    if (uploadState.state === "loading" || uploadState.state === "queued") return Loader2;
    if (uploadState.state === "ready") return CheckCircle2;
    if (uploadState.state === "error") return XCircle;
    return Upload;
  }, [uploadState.state]);
  const UploadStateIcon = uploadIcon;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <Bot size={28} />
          <div>
            <p className="eyebrow">DocuMind</p>
            <h1>Documentation RAG workbench</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <form className="api-base-form" onSubmit={handleApiBaseSave}>
            <Server size={16} />
            <input
              value={apiBaseInput}
              onChange={(event) => setApiBaseInput(event.target.value)}
              placeholder="https://documind-api.onrender.com"
              spellCheck="false"
            />
            <button type="submit">Save</button>
          </form>
          <div className={`status-pill ${health.state}`} title={health.error ?? "API status"}>
            <Activity size={16} />
            <span>{statusLabel}</span>
          </div>
        </div>
      </header>

      <section className="workspace">
        <aside className="sidebar-panel">
          <form className="upload-form" onSubmit={handleUpload}>
            <div className="section-heading">
              <FileText size={19} />
              <h2>Corpus</h2>
            </div>

            <label className="file-drop">
              <Upload size={22} />
              <span>{file ? file.name : "Select document"}</span>
              <input
                type="file"
                accept=".txt,.md,.markdown,.pdf"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>

            <div className="url-ingest-row">
              <Globe size={18} />
              <input
                value={url}
                onChange={(event) => setUrl(event.target.value)}
                placeholder="https://docs.example.com/page"
              />
              <button
                className="icon-button"
                type="button"
                disabled={!canIngestUrl}
                onClick={handleUrlIngest}
                title="Fetch URL"
              >
                {uploadState.state === "loading" && url.trim() ? (
                  <Loader2 className="spin" size={17} />
                ) : (
                  <Globe size={17} />
                )}
              </button>
            </div>

            <label className="toggle-row">
              <input
                type="checkbox"
                checked={asyncMode}
                onChange={(event) => setAsyncMode(event.target.checked)}
              />
              <span>Async</span>
            </label>

            <button className="primary-button" type="submit" disabled={!canUpload}>
              <Upload size={17} />
              <span>Ingest</span>
            </button>

            <div className={`inline-status ${uploadState.state}`}>
              <UploadStateIcon
                size={17}
                className={uploadState.state === "loading" || uploadState.state === "queued" ? "spin" : ""}
              />
              <span>{uploadState.message || "Ready"}</span>
            </div>
          </form>

          <div className="system-strip">
            <Server size={18} />
            <span>{health.data?.service ?? "documind-api"}</span>
          </div>

          <section className="corpus-summary">
            <div className="section-heading">
              <Database size={18} />
              <h2>Indexed</h2>
            </div>
            <div className="corpus-counts">
              <span>{corpusState.documents.length} docs</span>
              <span>{chunkTotal} chunks</span>
            </div>
            <div className="scope-strip">
              <span>{scopeLabel}</span>
              <button
                className="mini-button"
                type="button"
                disabled={scopedDocumentIds.length === 0}
                onClick={handleClearScope}
                title="Use all indexed documents"
              >
                <RotateCw size={14} />
              </button>
            </div>
            {corpusState.error && <p className="error-text">{corpusState.error}</p>}
            {corpusState.documents.length > 0 && (
              <div className="document-list">
                {corpusState.documents.slice(0, 4).map((document) => (
                  <label className="document-row" key={document.id} title={document.source_uri ?? document.title}>
                    <input
                      type="checkbox"
                      checked={scopedDocumentIds.includes(document.id)}
                      onChange={() => handleToggleDocument(document.id)}
                    />
                    <span>{document.title}</span>
                    <small>{document.chunks_created}</small>
                  </label>
                ))}
              </div>
            )}
            <button
              className="secondary-button danger"
              type="button"
              disabled={!canClearCorpus}
              onClick={handleClearCorpus}
            >
              <Trash2 size={16} />
              <span>Clear Corpus</span>
            </button>
          </section>

          <nav className="view-tabs" aria-label="Workspace view">
            <button
              type="button"
              className={activeView === "ask" ? "active" : ""}
              onClick={() => setActiveView("ask")}
            >
              <MessageSquareText size={16} />
              <span>Ask</span>
            </button>
            <button
              type="button"
              className={activeView === "eval" ? "active" : ""}
              onClick={() => setActiveView("eval")}
            >
              <BarChart3 size={16} />
              <span>Eval</span>
            </button>
          </nav>

          {history.length > 0 && (
            <section className="history-list">
              <div className="section-heading">
                <Clock3 size={18} />
                <h2>Recent</h2>
              </div>
              {history.map((item) => (
                <button
                  type="button"
                  key={`${item.question}-${item.answer.slice(0, 24)}`}
                  className="history-item"
                  onClick={() => setAnswerState({ state: "ready", data: item, error: null })}
                >
                  {item.question}
                </button>
              ))}
            </section>
          )}
        </aside>

        {activeView === "ask" ? (
          <section className="chat-panel">
            <div className="section-heading">
              <MessageSquareText size={20} />
              <h2>Ask</h2>
            </div>

            <form className="question-form" onSubmit={handleAsk}>
              <Search size={19} />
              <input
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about the indexed documentation"
              />
              <button className="icon-button" type="submit" disabled={!canAsk} title="Send question">
                {answerState.state === "loading" ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
              </button>
            </form>

            <article className={`answer-surface ${answerState.state}`}>
              {answerState.state === "idle" && <EmptyAnswer />}
              {answerState.state === "loading" && <LoadingAnswer />}
              {answerState.state === "error" && <p className="error-text">{answerState.error}</p>}
              {answerState.state === "ready" && answerState.data && (
                <AnswerView answer={answerState.data} />
              )}
            </article>

            <section className="sources-area">
              <div className="section-heading">
                <FileText size={18} />
                <h2>Sources</h2>
              </div>
              <div className="source-list">
                {latestSources.length === 0 ? (
                  <p className="muted-text">No sources selected</p>
                ) : (
                  latestSources.map((source, index) => (
                    <SourceItem key={source.chunk_id} source={source} index={index + 1} />
                  ))
                )}
              </div>
            </section>
          </section>
        ) : (
          <EvalDashboard
            casesText={evalCasesText}
            canRun={canRunEval}
            evalState={evalState}
            scopeLabel={scopeLabel}
            onCasesChange={setEvalCasesText}
            onRun={handleRunEval}
          />
        )}
      </section>
    </main>
  );
}

function EmptyAnswer() {
  return (
    <div className="empty-state">
      <Bot size={34} />
      <p>Upload documentation, then ask a question.</p>
    </div>
  );
}

function LoadingAnswer() {
  return (
    <div className="empty-state">
      <Loader2 className="spin" size={30} />
      <p>Retrieving sources</p>
    </div>
  );
}

function AnswerView({ answer }) {
  return (
    <>
      <div className="answer-meta">
        <span>{answer.cache_hit ? "cache hit" : "fresh answer"}</span>
        <span>{answer.citations.length} citations</span>
      </div>
      <p className="answer-text">{answer.answer}</p>
      <div className="citation-row">
        {answer.citations.map((citation) => (
          <a
            key={`${citation.marker}-${citation.chunk_id}`}
            href={citation.source_uri ?? `#${citation.chunk_id}`}
            title={citation.title}
          >
            {citation.marker}
          </a>
        ))}
      </div>
    </>
  );
}

function SourceItem({ source, index }) {
  return (
    <article className="source-item">
      <div className="source-head">
        <span>[{index}]</span>
        <strong>{source.title}</strong>
        <small>{source.score.toFixed(3)}</small>
      </div>
      <p>{source.content}</p>
    </article>
  );
}

function EvalDashboard({ casesText, canRun, evalState, scopeLabel, onCasesChange, onRun }) {
  const runs = evalState.data?.runs ?? [];

  return (
    <section className="eval-panel">
      <div className="eval-toolbar">
        <div className="section-heading">
          <BarChart3 size={20} />
          <h2>Eval Dashboard</h2>
        </div>
        <span className="scope-badge">{scopeLabel}</span>
        <button className="primary-button" type="button" disabled={!canRun} onClick={onRun}>
          {evalState.state === "loading" ? <Loader2 className="spin" size={17} /> : <Play size={17} />}
          <span>Run Eval</span>
        </button>
      </div>

      <section className="eval-grid">
        <label className="eval-editor">
          <span>Cases JSON</span>
          <textarea
            spellCheck="false"
            value={casesText}
            onChange={(event) => onCasesChange(event.target.value)}
          />
        </label>

        <article className={`eval-results ${evalState.state}`}>
          {evalState.state === "idle" && (
            <div className="empty-state">
              <Target size={34} />
              <p>Run retrieval and answer evaluation after indexing a corpus.</p>
            </div>
          )}
          {evalState.state === "loading" && (
            <div className="empty-state">
              <Loader2 className="spin" size={30} />
              <p>Evaluating retrieval and answer quality</p>
            </div>
          )}
          {evalState.state === "error" && <p className="error-text">{evalState.error}</p>}
          {evalState.state === "ready" && <EvalResults runs={runs} />}
        </article>
      </section>
    </section>
  );
}

function EvalResults({ runs }) {
  if (runs.length === 0) {
    return <p className="muted-text">No eval results returned.</p>;
  }

  const bestRun = [...runs].sort((a, b) => scoreRun(b) - scoreRun(a))[0];

  return (
    <div className="eval-result-stack">
      <div className="metric-grid">
        {runs.map((run) => (
          <MetricCard key={run.config.name} run={run} isBest={run.config.name === bestRun.config.name} />
        ))}
      </div>

      {runs.map((run) => (
        <section className="case-table-wrap" key={`cases-${run.config.name}`}>
          <div className="case-table-heading">
            <Gauge size={18} />
            <h3>{run.config.name}</h3>
          </div>
          <div className="case-table">
            <div className="case-row header">
              <span>Case</span>
              <span>Result</span>
              <span>Rank</span>
              <span>Faith</span>
              <span>Rel</span>
              <span>Terms</span>
            </div>
            {run.case_results.map((item) => (
              <div className="case-row" key={`${run.config.name}-${item.case_id}`}>
                <span title={item.question}>{item.case_id}</span>
                <span className={item.matched ? "pass" : "fail"}>
                  {item.matched ? "pass" : "miss"}
                </span>
                <span>{item.first_match_rank ?? "-"}</span>
                <span>{formatScore(item.faithfulness)}</span>
                <span>{formatScore(item.answer_relevance)}</span>
                <span>{item.matched_terms.length ? item.matched_terms.join(", ") : "-"}</span>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function MetricCard({ run, isBest }) {
  return (
    <article className={isBest ? "metric-card best" : "metric-card"}>
      <div className="metric-head">
        <strong>{run.config.name}</strong>
        <span>k={run.config.top_k}</span>
      </div>
      <MetricBar label="Recall" value={run.recall_at_k} />
      <MetricBar label="MRR" value={run.mean_reciprocal_rank} />
      <MetricBar label="Precision" value={run.mean_context_precision} />
      <MetricBar label="Faith" value={run.mean_faithfulness} />
      <MetricBar label="Relevance" value={run.mean_answer_relevance} />
    </article>
  );
}

function MetricBar({ label, value }) {
  const hasScore = typeof value === "number";
  const percentage = hasScore ? Math.round(value * 100) : 0;

  return (
    <div className="metric-bar-row">
      <div className="metric-label">
        <span>{label}</span>
        <strong>{hasScore ? `${percentage}%` : "-"}</strong>
      </div>
      <div className="metric-track">
        <span style={{ inlineSize: `${percentage}%` }} />
      </div>
    </div>
  );
}

function scoreRun(run) {
  const scores = [
    run.recall_at_k,
    run.mean_reciprocal_rank,
    run.mean_context_precision,
    run.mean_faithfulness,
    run.mean_answer_relevance,
  ].filter((value) => typeof value === "number");
  if (scores.length === 0) return 0;
  return scores.reduce((sum, value) => sum + value, 0) / scores.length;
}

function formatScore(value) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

export default App;
