#!/usr/bin/env bash

set -uo pipefail

KEYS='^(GEMINI|EMBED|CHUNK|TOP_K|THINKING|MAX_|REQUEST|LOG_|APP_|CHROMA|UPLOAD)'
mask() { sed 's/\(GEMINI_API_KEY=.\{6\}\).*/\1.../'; }

if curl -sf --max-time 2 http://localhost:8000/api/info >/dev/null 2>&1; then
  echo "Source: local app on http://localhost:8000"
  echo
  curl -s http://localhost:8000/api/info \
    | python3 -c 'import json,sys; [print(f"  {k:<16} {v}") for k,v in json.load(sys.stdin).items()]'
  echo
  echo "(/api/info reports the settings the process loaded, not raw env vars.)"
  exit 0
fi

if docker compose ps --status running --services 2>/dev/null | grep -qx app; then
  echo "Source: docker compose container 'app'"
  echo
  docker compose exec -T app env | grep -E "$KEYS" | mask | sort | sed 's/^/  /'
  exit 0
fi

POD=$(kubectl -n knowledge-assistant get pod -l app=kb-app \
        -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)

if [[ -n "${POD:-}" ]]; then
  echo "Source: kubernetes pod $POD"
  echo
  kubectl -n knowledge-assistant exec "$POD" -- env \
    | grep -E "$KEYS" | mask | sort | sed 's/^/  /'
  exit 0
fi

echo "Nothing is running, so this is .env on disk - not what any app loaded."
echo
if [[ -f .env ]]; then
  grep -E "$KEYS" .env | grep -v '^#' | mask | sort | sed 's/^/  /'
else
  echo "  no .env file here either - copy .env.example to .env"
fi
echo
echo "Start something first:  make run   |   make up   |   make k8s-deploy"
