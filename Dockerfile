# Three stages. Node builds the React bundle, Python builds the wheels, and
# the runtime image gets neither toolchain - just the artefacts.

FROM node:22-slim AS ui

WORKDIR /ui

# Lockfile first, so npm ci is cached independently of source changes.
# ci, not install: it installs exactly what the lockfile pins and fails if
# package.json and the lockfile disagree, which is what makes the build
# reproducible.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim

# Non-root. Pod security policies reject root containers in most real clusters,
# and there is no reason this app needs it.
RUN useradd --create-home --uid 10001 appuser

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY app/ ./app/
COPY --from=ui /ui/dist ./frontend_dist/

# Writable paths for the vector store and uploads. In Kubernetes a PVC mounts
# over /app/data; locally it's just a directory in the container.
RUN mkdir -p /app/data/chroma /app/data/uploads && chown -R appuser:appuser /app

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CHROMA_DIR=/app/data/chroma \
    UPLOAD_DIR=/app/data/uploads \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)"

# One worker, deliberately. ChromaDB's embedded mode is a single-writer
# SQLite file - a second uvicorn worker in this container would open the
# same index and corrupt it, exactly as a second pod would. Concurrency
# comes from async request handling, not from processes.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
