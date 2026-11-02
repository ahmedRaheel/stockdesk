#!/usr/bin/env bash
set -Eeuo pipefail
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}"
if [[ "${1:-}" == "--managed" ]]; then COMPOSE_FILE="compose.managed.yaml"; fi
COMPOSE=(docker compose -f "$COMPOSE_FILE")
echo "=== Compose file: $COMPOSE_FILE ==="
echo '=== Container states ==='
"${COMPOSE[@]}" ps -a || true
echo '=== Backend last 180 log lines ==='
"${COMPOSE[@]}" logs --no-color --tail=180 backend || true
echo '=== Backend health / restarts ==='
CID=$("${COMPOSE[@]}" ps -q backend || true)
if [[ -n "$CID" ]]; then
  docker inspect --format 'Status={{.State.Status}} ExitCode={{.State.ExitCode}} RestartCount={{.RestartCount}} Health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$CID" || true
  docker inspect --format '{{if .State.Health}}{{range .State.Health.Log}}[{{.End}}] exit={{.ExitCode}} {{.Output}}{{println}}{{end}}{{end}}' "$CID" || true
else
  echo 'Backend container not found.'
fi
if [[ "$COMPOSE_FILE" == 'compose.yaml' ]]; then
  echo '=== External postgres network (name can be configured with POSTGRES_NETWORK) ==='
  NETWORK="${POSTGRES_NETWORK:-chatbot-network}"
  docker network inspect "$NETWORK" --format 'Network={{.Name}} AttachedContainers={{len .Containers}}' 2>&1 || true
fi
printf '\nTo send for diagnosis: paste the backend logs and the health inspection output above.\n'
