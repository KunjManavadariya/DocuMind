from pydantic import BaseModel, Field


class IngestTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source_uri: str | None = None
    chunk_size: int = Field(default=256, ge=80, le=1200)
    chunk_overlap: int = Field(default=40, ge=0, le=400)


class IngestUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)
    chunk_size: int = Field(default=256, ge=80, le=1200)
    chunk_overlap: int = Field(default=40, ge=0, le=400)


class IngestTextResponse(BaseModel):
    document_id: str
    chunks_created: int


class IngestJobResponse(BaseModel):
    task_id: str
    status: str


class IngestJobStatusResponse(BaseModel):
    task_id: str
    status: str
    result: IngestTextResponse | None = None
    error: str | None = None


class DocumentSummary(BaseModel):
    id: str
    title: str
    source_type: str
    source_uri: str | None
    chunks_created: int
    created_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]


class CorpusClearResponse(BaseModel):
    documents_deleted: int
    chunks_deleted: int


class RetrieveRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_uri: str | None
    chunk_index: int
    score: float


class RetrieveResponse(BaseModel):
    question: str
    results: list[RetrievedChunk]


class AnswerRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    document_ids: list[str] = Field(default_factory=list)


class SourceCitation(BaseModel):
    marker: str
    chunk_id: str
    document_id: str
    title: str
    source_uri: str | None
    chunk_index: int
    score: float


class AnswerResponse(BaseModel):
    question: str
    answer: str
    citations: list[SourceCitation]
    sources: list[RetrievedChunk]
    cache_hit: bool = False


class EvalCase(BaseModel):
    id: str
    question: str = Field(min_length=1)
    expected_terms: list[str] = Field(default_factory=list)
    expected_source_uri: str | None = None
    expected_answer: str | None = None


class EvalConfig(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    top_k: int = Field(default=5, ge=1, le=20)


class EvalRunRequest(BaseModel):
    cases: list[EvalCase] = Field(min_length=1)
    configs: list[EvalConfig] = Field(default_factory=lambda: [EvalConfig(name="top-5", top_k=5)])
    document_ids: list[str] = Field(default_factory=list)


class EvalCaseResult(BaseModel):
    case_id: str
    question: str
    matched: bool
    recall_at_k: float
    reciprocal_rank: float
    context_precision: float
    faithfulness: float | None = None
    answer_relevance: float | None = None
    first_match_rank: int | None
    matched_terms: list[str]
    retrieved_sources: list[str | None]
    answer: str | None = None


class EvalRunResult(BaseModel):
    config: EvalConfig
    case_results: list[EvalCaseResult]
    recall_at_k: float
    mean_reciprocal_rank: float
    mean_context_precision: float
    mean_faithfulness: float | None = None
    mean_answer_relevance: float | None = None


class EvalRunResponse(BaseModel):
    runs: list[EvalRunResult]
