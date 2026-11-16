#!/usr/bin/env bash

set -uo pipefail

NS_APP=knowledge-assistant
NS_MON=monitoring
pids=()

cleanup() {
  echo
  echo "Stopping tunnels..."
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  exit 0
}
trap cleanup INT TERM

forward() {
  local label="$1" ns="$2" svc="$3" ports="$4" note="${5:-}"
  local port="${ports%%:*}"

  if ! kubectl -n "$ns" get "svc/$svc" >/dev/null 2>&1; then
    printf '  %-12s not deployed (skipping)\n' "$label"
    return
  fi

  local holder
  holder=$(lsof -ti:"$port" 2>/dev/null | head -1)

  if [[ -n "$holder" ]]; then
    if ps -p "$holder" -o comm= 2>/dev/null | grep -q kubectl; then
      kill "$holder" 2>/dev/null && sleep 1
      printf '  %-12s (replaced a stale forward)\n' "$label"
    else
      printf '  %-12s PORT %s IN USE by %s - not touching it\n' \
        "$label" "$port" "$(ps -p "$holder" -o comm= 2>/dev/null | xargs)"
      return
    fi
  fi

  kubectl -n "$ns" port-forward "svc/$svc" "$ports" >/dev/null 2>&1 &
  pids+=($!)
  printf '  %-12s http://localhost:%s  %s\n' "$label" "${ports%%:*}" "$note"
}

echo
echo "Starting port-forwards..."
echo

forward "app"        "$NS_APP" kb-app                                 8080:80
forward "prometheus" "$NS_MON" monitoring-kube-prometheus-prometheus  9090:9090
forward "grafana"    "$NS_MON" monitoring-grafana                     3000:80  "(admin/admin)"

echo
sleep 3

echo "Checking..."
for probe in "8080/healthz:app" "9090/-/healthy:prometheus" "3000/api/health:grafana"; do
  url="localhost:${probe%%:*}"
  name="${probe##*:}"
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null)
  [[ "$code" == "200" ]] \
    && printf '  %-12s ok\n' "$name" \
    || printf '  %-12s not responding (%s) - check the pod\n' "$name" "${code:-no reply}"
done

echo
echo "Ctrl-C stops all of them."
wait
