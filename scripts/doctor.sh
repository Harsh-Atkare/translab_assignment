#!/usr/bin/env bash

set -uo pipefail

ok=0
bad=0

pass() { printf '  \033[32mok\033[0m    %s\n' "$1"; ok=$((ok + 1)); }
fail() { printf '  \033[31mFAIL\033[0m  %s\n     → %s\n' "$1" "$2"; bad=$((bad + 1)); }
warn() { printf '  \033[33mwarn\033[0m  %s\n     → %s\n' "$1" "$2"; }

echo
echo "Project"

[[ -f requirements.txt && -d app ]] \
  && pass "running from the project root" \
  || fail "not in the project root" "cd into the folder with app/ and requirements.txt"

if [[ -f .env ]]; then
  if grep -qE '^GEMINI_API_KEY=.+' .env; then
    pass ".env exists and has a key"
  else
    fail ".env has no GEMINI_API_KEY" "add your key: https://aistudio.google.com/app/apikey"
  fi
else
  fail ".env is missing" "cp .env.example .env, then add your key"
fi

[[ -d frontend/dist ]] \
  && pass "frontend is built" \
  || warn "frontend not built" "make ui  (the API still works without it)"

echo
echo "Ports"

running=$(docker compose ps --status running --services 2>/dev/null || true)

for port in 8000 9090 3000; do
  case "$port" in
    8000) svc=app ;;
    9090) svc=prometheus ;;
    3000) svc=grafana ;;
  esac

  if grep -qx "$svc" <<<"$running" 2>/dev/null; then
    pass "port $port - our own '$svc' container"
  elif lsof -ti:"$port" >/dev/null 2>&1; then
    owner=$(lsof -ti:"$port" | head -1 | xargs ps -p 2>/dev/null | tail -1 | awk '{for(i=4;i<=NF;i++) printf "%s ", $i}')
    warn "port $port is in use${owner:+ by:$owner}" "lsof -ti:$port | xargs kill   (or stop 'make run' first)"
  else
    pass "port $port is free"
  fi
done

echo
echo "Docker"

if ! command -v docker >/dev/null 2>&1; then
  fail "docker is not installed" "https://docker.com/products/docker-desktop"
elif ! docker info >/dev/null 2>&1; then
  fail "docker daemon is not running" "start Docker Desktop and wait for the whale to stop animating"
else
  pass "docker daemon is running"

  docker compose version >/dev/null 2>&1 \
    && pass "docker compose is available" \
    || fail "docker compose not found" "update Docker Desktop - compose v2 ships with it"
fi

echo
echo "Toolchain"

command -v python3 >/dev/null && pass "python3 $(python3 -V 2>&1 | awk '{print $2}')" \
  || fail "python3 not found" "brew install python@3.12"

if command -v node >/dev/null; then
  major=$(node -v | sed 's/v\([0-9]*\).*/\1/')
  [[ "$major" -ge 22 ]] \
    && pass "node $(node -v)" \
    || fail "node $(node -v) is too old" "need 22+: brew upgrade node"
else
  fail "node not found" "brew install node  (needed for the frontend build)"
fi

[[ -d .venv ]] && pass "virtualenv exists" || warn "no .venv" "make venv"

echo
if [[ "$bad" -eq 0 ]]; then
  echo "All clear. make run   (local)   |   make up   (docker)"
else
  echo "$bad problem(s) to fix above."
fi
echo
exit 0
