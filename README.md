# Enterprise AI Knowledge Assistant

Upload PDF documents, ask questions in plain English, get answers grounded in
those documents with page citations.

Built as an end-to-end exercise: a RAG application with a React frontend,
containerised, deployed on Kubernetes, with CI/CD, centralised logging and a
Grafana dashboard.

---

## What it does

1. You upload a PDF. The text is extracted page by page, cleaned, and split
   into overlapping chunks of roughly 1200 characters.
2. Each chunk is embedded with Gemini and stored in ChromaDB alongside its
   page number and source filename.
3. You ask a question. The question is embedded, the four closest chunks are
   retrieved by cosine similarity, and those chunks plus the question go to
   Gemini.
4. The answer comes back citing the pages it used, with the retrieved
   passages and a per-stage timing breakdown. If nothing relevant is found,
   it says so rather than inventing an answer.

---

## Architecture

```
                    ┌──────────────────────────┐
  React 18 + Vite   │  FastAPI  (app/main.py)  │
  (served by        │  ├─ /api/documents       │
   FastAPI) ──────► │  ├─ /api/ask             │
                    │  ├─ /healthz  /readyz    │
                    │  └─ /metrics             │
                    └────┬────────────────┬────┘
                         │                │
               ┌─────────▼──────┐   ┌─────▼──────────┐
               │   PyMuPDF      │   │  Gemini API    │
               │   extract +    │   │  embeddings +  │
               │   chunk        │   │  generation    │
               └─────────┬──────┘   └─────┬──────────┘
                         │                │
                    ┌────▼────────────────▼────┐
                    │  ChromaDB (persistent)   │
                    │  vectors + page metadata │
                    └──────────────────────────┘

  Observability:  stdout JSON logs ──► Promtail ──► Loki ──► Grafana
                  /metrics          ──► Prometheus ───────► Grafana
```

### Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI | Async, automatic OpenAPI docs, tiny |
| Frontend | React 18 + Vite | Built in its own Docker stage, served as static files |
| Answer rendering | react-markdown + remark-gfm | Answers are markdown; tables and code need a real parser |
| PDF | PyMuPDF | Fastest pure-Python extraction, keeps page numbers |
| Embeddings | Gemini `gemini-embedding-2` | Free tier, no local model to ship |
| Vector store | ChromaDB (embedded) | Persists to disk, no extra service to run |
| LLM | Gemini Flash | Free tier, fast enough for interactive use |
| Metrics | prometheus-fastapi-instrumentator | Standard histograms with four lines of setup |
| Logs | JSON to stdout | Whatever collects container logs can parse them |

---

## Prerequisites

- **Python 3.12+**
- **Node 22+** — the frontend is a Vite build
- Docker Desktop (for the container and compose steps)
- minikube or kind, plus kubectl (for the Kubernetes step)
- A Gemini API key — free, no credit card, from
  [Google AI Studio](https://aistudio.google.com/app/apikey)

---

## 1. Run locally

```bash
git clone <repo-url>
cd translab_assignment

cp .env.example .env
# open .env and paste your GEMINI_API_KEY

make venv     # python deps + npm install + vite build
make run
```

Open <http://localhost:8000>.

Confirm your key can reach both models before uploading anything:

```bash
make models   # lists what the key has access to
```

`GEMINI_MODEL` must appear under GENERATION and `GEMINI_EMBED_MODEL` under
EMBEDDING. A name that isn't on the list fails at request time with a 404,
not at startup.

### Working on the frontend

```bash
make ui-dev   # Vite on :5173, hot reload, proxies /api to :8000
make run      # in another terminal
```

`make ui` does a one-off production build into `frontend/dist`, which is what
`make run` and the Docker image serve.

`make test` does not build the frontend — the suite shouldn't need Node. On
a fresh clone `/` returns 503 with "Frontend not built. Run `make ui`", and
the test asserts that; once built it asserts the page is served. The API,
`/docs` and `/metrics` work either way.

### Tests

```bash
make test     # 64 tests, no network calls - Gemini is stubbed
make lint
```

---

## 2. The interface

A two-column workspace rather than a chat window.

- **Sources rail** — drag-and-drop upload, the list of indexed documents with
  their chunk counts, and per-document removal.
- **Errors as a toast** — failures appear in a dismissible popup carrying
  the server's own message, not inline where they would read like the
  model's answer. Auto-hides after 8 seconds, Escape closes it, and the
  question stays in the box so you can just press Ask again.
- **Answer column** — each exchange is a numbered entry separated by a rule:
  question set in a serif, answer revealed with a typewriter effect, the
  retrieved passages as collapsible rows showing page number and similarity
  score, and a timing breakdown underneath.
- **Markdown rendering.** Gemini answers technical questions with numbered
  steps, bold labels, tables and fenced shell commands. Those are rendered
  properly — code blocks get a copy button, and `[page 15]` citations become
  chips matching the sources panel.
- **Light theme by default**, dark behind the toggle, remembered per browser
  in `localStorage`.

Upload shows the four real pipeline stages with an indeterminate bar. The
server does extraction, chunking, embedding and indexing inside one request,
so there is no genuine percentage to report — the bar stays indeterminate
rather than showing a number that would be invented.

---

## 3. Run with Docker

The image is built in three stages: Node compiles the React bundle, a Python
stage builds wheels, and the runtime image copies in the artefacts from both.
Neither toolchain ships — no compilers, no npm, no `node_modules`.

Single container:

```bash
docker build -t translab-assignment:local .
docker run --rm -p 8000:8000 --env-file .env translab-assignment:local
```

Full stack with Prometheus and Grafana:

```bash
make doctor   # checks Docker, .env, ports and versions first
make up
```

Note that `make run` and `make up` both want port 8000, so stop one before
starting the other.

| Service | URL | Credentials |
|---|---|---|
| App | <http://localhost:8000> | — |
| Prometheus | <http://localhost:9090> | — (check **Status → Target health**) |
| Grafana | <http://localhost:3000> | admin / admin |

The dashboard is provisioned automatically. `make load` sends some traffic so
the panels have data in them.

### Rebuilding vs restarting

`.env` is never baked into the image — it is in `.dockerignore`, and the
values are injected at container start. So a config change does not need a
rebuild:

| You changed | Command | Why |
|---|---|---|
| `.env` only | `make restart` | Recreates the container with the new values. Seconds |
| Python or React source | `make rebuild` | Image has to be rebuilt first |
| Nothing, just stopped it | `make up` | Reuses the existing image |

`make env-check` prints the config the app is actually using, with the API
key masked. It looks for a local uvicorn first, then the compose stack, then
a Kubernetes pod, and says which one it found — so the same command answers
"did my change land?" wherever the app happens to be running.

```bash
make down     # stop everything
```

---

## 4. Deploy on Kubernetes

Tested on minikube.

```bash
minikube start --cpus=4 --memory=4096
minikube addons enable ingress

make k8s-load      # build the image into minikube's docker daemon
make k8s-deploy    # namespace, secret, configmap, pvc, deployment, svc, ingress
make k8s-status
```

Reach the app:

```bash
make k8s-forward   # then http://localhost:8080
```

or through the ingress:

```bash
minikube tunnel                     # separate terminal, needs sudo
# then http://kb.127.0.0.1.nip.io
```

### Manifests

| File | What it does |
|---|---|
| `namespace.yaml` | Isolates everything in `knowledge-assistant` |
| `configmap.yaml` | Non-secret config — models, chunking, throughput, paths |
| `secret.example.yaml` | Template; the real secret is created from the CLI |
| `pvc.yaml` | 2 Gi volume for the Chroma index |
| `deployment.yaml` | 1 replica, non-root, startup/liveness/readiness probes |
| `service.yaml` | ClusterIP on port 80 |
| `ingress.yaml` | nginx, 20 MB body limit for PDF uploads |
| `servicemonitor.yaml` | Prometheus scrape target (needs kube-prometheus-stack) |

**On replica count:** this runs as a single replica by design. ChromaDB's
embedded mode writes to a SQLite file on a ReadWriteOnce volume, so two pods
would corrupt it — which is also why the deployment uses the `Recreate`
strategy rather than a rolling update. Scaling horizontally means switching
to Chroma in server mode or a hosted vector database: a deliberate trade-off
for a project of this size, not an oversight.

**Probes.** Liveness hits `/healthz`, which deliberately does no I/O — if it
touched Chroma or Gemini, a slow dependency would get the pod killed and make
an outage worse. Readiness hits `/readyz`, which does check them. A startup
probe runs first so a cold Chroma index doesn't get the pod killed mid-boot.

---

## 5. Monitoring and logging

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/prometheus-values.yaml

helm install loki grafana/loki-stack \
  -n monitoring -f monitoring/loki-values.yaml

kubectl apply -f k8s/servicemonitor.yaml
```

Load the dashboard into Grafana:

```bash
kubectl -n monitoring port-forward svc/monitoring-grafana 3000:80
# Grafana → Dashboards → Import → upload
# monitoring/dashboards/knowledge-assistant.json
```

### What's on the dashboard

Thirteen panels across three rows: request rate, 5xx error rate, p95 latency,
documents indexed and chunks stored as stat tiles; request rate by endpoint
and p50/p95/p99 HTTP latency; question-answering latency, ingestion latency,
responses by status code, pipeline errors by stage, process memory, and a
stacked breakdown of where query time actually goes — embedding the question
vs. vector search vs. generation.

That last panel is the useful one. Knowing a question took six seconds tells
you nothing; knowing that 5.8 of them were the model tells you where to look.

### Custom metrics

| Metric | Type | Meaning |
|---|---|---|
| `kb_ingest_duration_seconds` | histogram | Parse + embed + index one PDF |
| `kb_query_duration_seconds` | histogram | Question to answer, end to end |
| `kb_stage_duration_seconds{stage}` | histogram | Query split into embed / search / generate |
| `kb_chunks_indexed_total` | counter | Chunks written to the store |
| `kb_documents_total` | gauge | Documents currently indexed |
| `kb_errors_total{stage}` | counter | Failures by pipeline stage |

### Logging

Every log line is a JSON object on stdout, carrying a `request_id` that is
also returned in the `X-Request-ID` response header. Promtail picks the lines
up off the node and ships them to Loki, so one request can be traced across
the whole chain in Grafana:

```logql
{namespace="knowledge-assistant"} | json | request_id="a1b2c3d4e5f6"
```

Nothing is written to a log file inside the container, which is what makes
this work without any app-side collector.

---

## 6. CI/CD

`.github/workflows/ci-cd.yml` runs on every push and pull request:

| Job | Does |
|---|---|
| `test` | ruff lint, Vite production build, pytest with coverage |
| `validate-manifests` | kubeconform against the Kubernetes schema |
| `build` | Builds and pushes to GitHub Container Registry, with layer caching |
| `deploy` | Dry run — prints the rollout commands |

The frontend build runs in CI so a broken UI fails the pipeline rather than
shipping in an image.

The build job authenticates with the automatically provided `GITHUB_TOKEN`,
so there are no secrets to configure. On a new repository it needs
**Settings → Actions → General → Workflow permissions → Read and write**.

The deploy job is a dry run on purpose: the cluster for this project is
minikube on a laptop, which GitHub's hosted runners cannot reach. The real
`kubectl` commands are in the workflow, commented out, and need only a
`KUBE_CONFIG` secret to go live against a reachable cluster.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | Upload and index a PDF (multipart) |
| `GET` | `/api/documents` | List indexed documents |
| `DELETE` | `/api/documents/{id}` | Remove a document and its chunks |
| `POST` | `/api/ask` | Ask a question |
| `GET` | `/api/info` | Current config and index size |
| `GET` | `/healthz` | Liveness — no I/O |
| `GET` | `/readyz` | Readiness — checks store and key |
| `GET` | `/metrics` | Prometheus exposition |
| `GET` | `/docs` | Swagger UI |

```bash
curl -F "file=@contract.pdf" http://localhost:8000/api/documents

curl -X POST http://localhost:8000/api/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the notice period?"}'
```

---

## Configuration

Everything is an environment variable; see `.env.example`. In Kubernetes the
non-secret values come from `k8s/configmap.yaml`, so change them there too.

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | Required |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Google renames models often — `make models` |
| `GEMINI_EMBED_MODEL` | `gemini-embedding-2` | Must match `EMBED_DIM` |
| `EMBED_DIM` | `768` | Changing this invalidates the existing index |
| `CHUNK_SIZE` | `1200` | Characters |
| `CHUNK_OVERLAP` | `200` | Stops answers being cut at a chunk boundary |
| `TOP_K` | `4` | Chunks sent to the model as context |
| `EMBED_CONCURRENCY` | `8` | Parallel embedding requests on the fallback path |
| `EMBED_RPM` | `90` | Requests/minute ceiling, to stay inside the free tier |
| `MAX_OUTPUT_TOKENS` | `2048` | Generation budget |
| `THINKING_BUDGET` | `0` | Reasoning tokens. `auto` lets the model decide |
| `REQUEST_TIMEOUT` | `120` | Seconds; ceiling on any single Gemini call |
| `MAX_UPLOAD_MB` | `20` | Must stay ≤ the ingress body limit |
| `CHROMA_DIR` | `./data/chroma` | Index location; the PVC mounts here in K8s |
| `UPLOAD_DIR` | `./data/uploads` | Scratch space for incoming files |
| `CHROMA_COLLECTION` | `documents` | Collection name inside Chroma |
| `APP_ENV` | `local` | Label only — shows up in logs and `/api/info` |
| `LOG_LEVEL` | `INFO` | Standard Python levels |
| `LOG_JSON` | `true` | `false` gives readable logs locally |

### Changing the embedding model

Vectors produced by two different embedding models are not comparable, so an
index built by one is meaningless to another. The app stamps the model and
dimension into the collection's metadata on creation and refuses to serve a
mismatched index, rather than silently returning nothing for every question:

```bash
make reset        # local: clears data/chroma
make k8s-reset    # cluster: recreates the PVC
```

Then re-upload the documents. The same applies to changing `EMBED_DIM`.

### Embedding throughput

**Not every embedding model batches.** The multimodal ones read a list of
strings as one interleaved input and return a single vector, rather than one
per string — which used to surface as `Unequal lengths for fields` from
Chroma. The app detects the mismatch on the first call, logs it once, and
falls back to one request per chunk.

Those requests run in parallel through a thread pool bounded by
`EMBED_CONCURRENCY`, with a sliding-window rate limiter set by `EMBED_RPM`.
Most of the time per request is network wait, so concurrency collapses it: on
a 49-chunk document with 400 ms latency, serial takes 20 s and the default
concurrency of 8 takes 3.2 s.

Raise `EMBED_CONCURRENCY` on a paid key. If you start seeing 429s, lower
`EMBED_RPM` instead — the limiter paces the requests rather than letting them
fail.

### Thinking models

Gemini 2.5 and 3.x models reason internally before writing, and that
reasoning is charged against `max_output_tokens`. With a small budget the
model can consume all of it thinking, return `finish_reason=MAX_TOKENS` with
no text at all, and do it slowly — a 35-second wait for an empty answer.

`THINKING_BUDGET=0` turns reasoning off, which is the right default here: the
answer already sits in the retrieved passages, so reasoning mostly adds
latency. Set it to `auto` to let the model decide, and raise
`MAX_OUTPUT_TOKENS` if you do.

The app also refuses to return an empty answer — it raises with the finish
reason and what to change, rather than rendering a blank reply.

### When Google is overloaded

`503 UNAVAILABLE — "This model is currently experiencing high demand"` comes
from Google, not from your quota, and it is common on the newest models at
busy times. The app handles it in three layers:

Google reports this two ways: **503 UNAVAILABLE** when the model is
saturated, and **504 DEADLINE_EXCEEDED** when their backend gives up
part-way through generating. Both are Google's state, and the 504 is their
deadline rather than any client setting — it arrives as a server error with
a JSON body, which a client-side timeout could never produce.

The app does not retry either one. Demand spikes routinely outlast any
reasonable backoff, so retrying buys a 30-second wait and the same failure.
It fails immediately and says why:

> The model is busy and could not finish in time. This is on Google's side
> and usually clears within a minute — try again. If it keeps happening,
> switch GEMINI_MODEL to a lighter model.

The raw SDK exception is a JSON blob; it goes to the logs, as a single line
rather than a traceback, because this is Google's state and not a bug here.
The user sees the sentence, in a toast.

### Free-tier quotas

A 429 is a different failure, and there are two kinds wearing the same code:

- **Per-minute rate limit** — clears in under a minute, so it is retried.
- **Per-day quota** — the free tier allows as few as **20 generate_content
  requests per day for a single model**. Google's `retryDelay` for this is
  measured in hours, so retrying is pointless; the app detects it and fails
  immediately with the reset time instead of waiting.

The daily quota is scoped **per project per model**
(`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), so switching
`GEMINI_MODEL` to a different Flash model gives a fresh allowance, and a new
project gives a fresh allowance for every model. Quotas reset at midnight
Pacific time.

Google also retires models and restricts older ones to existing keys, so a
name that worked last month can return 404 for a new key. `make models` is
the only reliable source for what a given key can reach.

The user-facing message says how long until the reset and what to change:

> This model's daily free-tier quota is used up. It resets in about 22h 21m.
> The quota is per model, so switching GEMINI_MODEL to another Flash model
> gives you a fresh allowance today.

### Why generation is logged twice

Generation is logged **before** it starts as well as after, with the model
and prompt size. Without the leading line, a slow call and an idle app look
identical in the logs — which is exactly how a 35-second wait went
undiagnosed once.

---

## Design decisions worth calling out

- **Grounding over fluency.** Three layers stop hallucination: the prompt
  forbids answering outside the supplied context, temperature is 0.2, and any
  query whose best match scores below 0.25 is refused before the model is
  called at all.
- **Cosine similarity**, because Gemini embeddings are normalised — that is
  the metric they were trained for.
- **1200-character chunks with 200 overlap.** Roughly 300 tokens: large
  enough to hold a complete idea, small enough that four fit in context
  without diluting the relevant part. The overlap stops a sentence spanning a
  boundary from being lost by both chunks.
- **Page numbers travel with every chunk**, which is what makes citations
  possible. Without them the sources panel would be decorative.
- **Fail loudly, not quietly.** Mismatched embedding models, empty model
  responses and wrong vector counts all raise with an actionable message. The
  alternative — an app that keeps serving and returns nothing useful — is far
  harder to debug.
- **A maintained markdown parser, not a hand-rolled one.** Answers to
  technical questions come back as numbered steps, tables and fenced
  commands; `react-markdown` handles them. The one piece of custom logic is
  closing an unterminated code fence while the typewriter is mid-block,
  without which the parser swallows the rest of the answer.
- **Tests never touch the network.** Gemini is stubbed throughout, so the
  suite runs offline, costs no quota, and is deterministic in CI. Most of
  the tests exist because something actually broke — the batching, empty
  answer, config and store-guard modules are all regression suites.

---

## Production readiness

Honest answer: **this is not production software, and it is not pretending
to be.** It is an assessment project built with production practices, which
is a different thing. Here is the split.

### What is genuinely production-grade

| Area | What's in place |
|---|---|
| Reproducible builds | Every Python dependency pinned; `npm ci` against a committed lockfile |
| Image hygiene | Three-stage build, no compilers or `node_modules` in the runtime layer, non-root UID 10001, dropped capabilities, `HEALTHCHECK` |
| Config | Everything from the environment, nothing hardcoded; secrets never in the image or in git |
| Health | Separate liveness (no I/O) and readiness (checks dependencies) endpoints, plus a startup probe |
| Observability | Prometheus metrics with per-stage histograms, structured JSON logs to stdout, request-id correlation through to Loki |
| Resilience | Fail-fast on upstream errors, classified by cause, actionable messages instead of stack traces |
| Correctness | 64 tests, no network dependency, run in CI on every push alongside lint and manifest validation |

### What would have to change for real production

| Gap | Why it matters | What you'd do |
|---|---|---|
| **No authentication** | Anyone who reaches the service can upload and query | OIDC or an API gateway in front; per-tenant document isolation |
| **Single replica** | No HA; a node drain is an outage | Chroma in server mode or a managed vector DB, then scale out |
| **No TLS on the ingress** | Traffic is plaintext | cert-manager with Let's Encrypt, or terminate at the load balancer |
| **No image scanning** | Vulnerable base layers ship unnoticed | Trivy or Grype in CI, failing on HIGH |
| **No backup of the index** | A lost PVC means re-uploading everything | Scheduled volume snapshots, or treat the index as rebuildable and keep the source PDFs |
| **Secrets are plain Kubernetes Secrets** | Base64, not encryption | External Secrets Operator or a cloud secret manager |
| **Free-tier model quota** | 429s and 503s under any real load | A paid key, and a queue in front of ingestion |
| **Deploy job is a dry run** | Nothing is actually rolled out | A reachable cluster and a `KUBE_CONFIG` secret |

None of these are hard to add. They are out of scope for a project sized to
be built and reviewed in a week, and saying so is more useful than pretending
otherwise.

### Why one worker, not four

The container runs `uvicorn --workers 1` on purpose. ChromaDB's embedded mode
is a single-writer SQLite file: a second worker process in the same container
would open the same index and corrupt it, exactly as a second pod would.
Concurrency comes from async request handling, not from processes. Lifting
that limit is the same change as lifting the single-replica limit.

---

## Known limitations

- **Scanned PDFs are rejected.** There is no OCR; the app returns a clear
  error rather than indexing an empty document.
- **Single replica.** See the note under Kubernetes.
- **Free-tier rate limits and upstream capacity.** Gemini's free tier
  throttles per minute (429), allows as few as 20 generations per day per
  model, and Google's models sometimes run out of capacity entirely (503).
  The app reports each clearly but cannot engineer them away on a free key.
- **No authentication.** Anyone who can reach the service can upload and
  query. A real deployment needs auth in front of it.
- **No streaming.** The answer arrives in one response; the typewriter effect
  is cosmetic, not token streaming.
- **Deploy stage is a dry run.** By design — no reachable cluster.

### What I'd do next

Authentication in front of the API, OCR for scanned PDFs, a reranker between
retrieval and generation to improve precision, streamed responses so the
first words arrive sooner, and Chroma in server mode so the deployment can
scale past one replica.

---

## Project layout

```
app/                      FastAPI application
  main.py                 App, middleware, routing, static serving
  config.py               Every setting, read from the environment
  logging_setup.py        JSON logs + request-id context
  metrics.py              Custom Prometheus metrics
  rag/
    pdf.py                Extract, clean, chunk (keeps page numbers)
    gemini.py             Embeddings + generation, rate limiting, error mapping
    store.py              ChromaDB wrapper + embedding fingerprint guard
    pipeline.py           ingest() and ask()
  routes/                 documents, chat, health
frontend/                 React 18 + Vite
  src/
    App.jsx               Layout and state
    api.js                Fetch wrapper
    hooks.js              Theme, typewriter, elapsed timer
    components/
      DocumentRail.jsx    Sources list
      UploadPanel.jsx     Dropzone + staged progress
      Entry.jsx           One question/answer block
      Answer.jsx          Markdown, code blocks, citation chips
tests/                    64 tests, Gemini stubbed throughout
  test_api.py             Upload, list, delete, ask, validation
  test_chunking.py        Splitting, overlap, page numbers, scanned PDFs
  test_config.py          .env loading and precedence
  test_embed_batching.py  Batching detection and per-chunk fallback
  test_empty_answer.py    Thinking-model budget exhaustion, safety blocks
  test_health.py          Probes, metrics, serving the UI built or not
  test_logging.py         JSON shape, third-party noise suppression
  test_rate_limiter.py    Token bucket, thread safety
  test_store_guard.py     Embedding-model fingerprint mismatch
  test_daily_quota.py     Per-day vs per-minute 429 and their messages
  test_overload.py        503 fail-fast and user-facing messages
  test_generation_logging.py  Logging before and after the model call
k8s/                      Kubernetes manifests
monitoring/               Prometheus, Grafana and Loki config + dashboard JSON
scripts/                  list_models, env-check, doctor, load generator, scaffold
.github/workflows/        CI/CD pipeline
```

Run `make help` to see every available command.
