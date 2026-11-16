#!/usr/bin/env bash

set -euo pipefail

BASE="${1:-http://localhost:8000}"
REQUESTS="${2:-40}"

QUESTIONS=(
  "What is the notice period?"
  "Summarise the key obligations."
  "How much annual leave is there?"
  "Who are the parties to this agreement?"
  "What happens on termination?"
)

echo "Sending ${REQUESTS} requests to ${BASE}"

for i in $(seq 1 "$REQUESTS"); do
  curl -s -o /dev/null "$BASE/healthz"
  curl -s -o /dev/null "$BASE/api/documents"

  if (( i % 5 == 0 )); then
    q="${QUESTIONS[$((RANDOM % ${#QUESTIONS[@]}))]}"
    curl -s -o /dev/null -X POST "$BASE/api/ask" \
      -H 'Content-Type: application/json' \
      -d "{\"question\":\"${q}\"}"
    printf '?'
  else
    printf '.'
  fi

  sleep 0.4
done

echo
echo "Done. Check Grafana."
