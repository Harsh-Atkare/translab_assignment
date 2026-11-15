from prometheus_client import Counter, Gauge, Histogram

LATENCY_BUCKETS = (0.5, 1, 2, 3, 5, 8, 12, 20, 30, 60)

INGEST_SECONDS = Histogram(
    "kb_ingest_duration_seconds",
    "Time to parse, embed and index one PDF",
    buckets=LATENCY_BUCKETS,
)

QUERY_SECONDS = Histogram(
    "kb_query_duration_seconds",
    "End to end time for a question, including retrieval and generation",
    buckets=LATENCY_BUCKETS,
)

STAGE_SECONDS = Histogram(
    "kb_stage_duration_seconds",
    "Time spent in each stage of answering a question",
    ["stage"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 8, 12, 20),
)

CHUNKS_INDEXED = Counter(
    "kb_chunks_indexed_total",
    "Chunks written to the vector store",
)

DOCUMENTS_TOTAL = Gauge(
    "kb_documents_total",
    "Documents currently in the vector store",
)

ERRORS = Counter(
    "kb_errors_total",
    "Unhandled errors by stage",
    ["stage"],
)
