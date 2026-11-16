.DEFAULT_GOAL := help
SHELL := /bin/bash

IMAGE  ?= translab-assignment
TAG    ?= local
NS     ?= knowledge-assistant

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'


.PHONY: venv
venv:  ## Create the virtualenv and install everything (python + node)
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -r requirements-dev.txt
	$(MAKE) ui

.PHONY: ui
ui:  ## Build the React frontend into frontend/dist
	cd frontend && npm install --no-audit --no-fund && npm run build

.PHONY: ui-dev
ui-dev:  ## Vite dev server on :5173 with hot reload (run `make run` too)
	cd frontend && npm run dev

.PHONY: run
run: frontend/dist  ## Run with autoreload on http://localhost:8000
	./.venv/bin/uvicorn app.main:app --reload --port 8000

frontend/dist:
	$(MAKE) ui

.PHONY: test
test:  ## Run the test suite
	./.venv/bin/pytest -v

.PHONY: lint
lint:  ## Lint with ruff
	./.venv/bin/ruff check app tests

.PHONY: env-check
env-check:  ## Show the config the app is using (local, docker or k8s)
	@./scripts/env-check.sh

.PHONY: models
models:  ## List the Gemini models your API key can actually use
	./.venv/bin/python scripts/list_models.py

.PHONY: reset
reset:  ## Wipe the vector index (needed after changing the embedding model)
	rm -rf data/chroma
	@echo "Index cleared - re-upload your documents."

.PHONY: load
load:  ## Fire some traffic so the Grafana panels have data
	./scripts/load.sh


.PHONY: build
build:  ## Build the image (--pull so base-image security patches land)
	docker build --pull -t $(IMAGE):$(TAG) .

define preflight
	@docker info > /dev/null 2>&1 || { \
		echo "Docker is not running. Start Docker Desktop, then try again."; \
		echo "Run 'make doctor' to check everything at once."; exit 1; }
	@test -f .env || { \
		echo "No .env file. Run: cp .env.example .env   then add your key."; exit 1; }
	@if ! docker compose ps --status running --services 2>/dev/null | grep -qx app; then \
		lsof -ti:8000 > /dev/null 2>&1 && { \
			echo "Port 8000 is in use by something that is not this stack -"; \
			echo "most likely 'make run' in another terminal. Stop it there, or:"; \
			echo "    lsof -ti:8000 | xargs kill"; exit 1; }; \
	fi; true
endef

.PHONY: doctor
doctor:  ## Check why `make up` or `make run` won't start
	@./scripts/doctor.sh

.PHONY: up
up:  ## Start app + Prometheus + Grafana
	$(preflight)
	docker compose up --build -d
	@echo "app        http://localhost:8000"
	@echo "prometheus http://localhost:9090"
	@echo "grafana    http://localhost:3000  (admin/admin)"

.PHONY: restart
restart:  ## Pick up .env changes - no rebuild (config only)
	$(preflight)
	docker compose up -d --force-recreate app
	@echo "app restarted with the current .env"

.PHONY: rebuild
rebuild:  ## Rebuild the image and restart (after a code or frontend change)
	$(preflight)
	docker compose up -d --build --force-recreate app
	@echo "app rebuilt and restarted"

.PHONY: down
down:  ## Stop the compose stack
	docker compose down

.PHONY: logs
logs:  ## Tail app logs
	docker compose logs -f app


.PHONY: k8s-load
k8s-load: build  ## Build and push the image into minikube's docker daemon
	minikube image load $(IMAGE):$(TAG)

.PHONY: k8s-secret
k8s-secret:  ## Create the API key secret from your .env
	@set -a && source .env && set +a && \
	kubectl create secret generic kb-secrets -n $(NS) \
		--from-literal=GEMINI_API_KEY="$$GEMINI_API_KEY" \
		--dry-run=client -o yaml | kubectl apply -f -

.PHONY: k8s-deploy
k8s-deploy:  ## Apply all manifests
	kubectl apply -f k8s/namespace.yaml
	$(MAKE) k8s-secret
	kubectl apply -f k8s/configmap.yaml -f k8s/pvc.yaml \
		-f k8s/deployment.yaml -f k8s/service.yaml -f k8s/ingress.yaml
	kubectl -n $(NS) rollout status deployment/kb-app --timeout=180s

.PHONY: k8s-status
k8s-status:  ## Show what's running
	kubectl -n $(NS) get pods,svc,ingress,pvc

.PHONY: k8s-logs
k8s-logs:  ## Tail pod logs
	kubectl -n $(NS) logs -l app=kb-app -f --tail=100

.PHONY: k8s-forward
k8s-forward:  ## Port-forward app, Prometheus and Grafana together
	@./scripts/k8s-forward.sh

.PHONY: k8s-dashboard
k8s-dashboard:  ## Load the Grafana dashboard into the cluster
	@kubectl -n monitoring create configmap kb-dashboard \
		--from-file=monitoring/dashboards/knowledge-assistant.json \
		--dry-run=client -o yaml | kubectl apply -f -
	@kubectl -n monitoring label configmap kb-dashboard grafana_dashboard=1 --overwrite
	@echo "Loaded. Grafana's sidecar picks it up within ~30s - then refresh."

.PHONY: k8s-urls
k8s-urls:  ## Print the service URLs
	@echo "  app         http://localhost:8080"
	@echo "  prometheus  http://localhost:9090"
	@echo "  grafana     http://localhost:3000  (admin/admin)"
	@echo
	@echo "  Start them with: make k8s-forward"

.PHONY: k8s-reset
k8s-reset:  ## Wipe the in-cluster index (after an embedding model change)
	kubectl -n $(NS) scale deployment/kb-app --replicas=0
	kubectl -n $(NS) delete pvc kb-data
	kubectl apply -f k8s/pvc.yaml
	kubectl -n $(NS) scale deployment/kb-app --replicas=1
	kubectl -n $(NS) rollout status deployment/kb-app --timeout=180s

.PHONY: k8s-clean
k8s-clean:  ## Delete everything in the namespace
	kubectl delete namespace $(NS) --ignore-not-found
