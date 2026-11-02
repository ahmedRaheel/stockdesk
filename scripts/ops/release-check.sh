#!/usr/bin/env bash
# Release checks for a live, configured deployment. No writes to business tables.
set -Eeuo pipefail
COMPOSE_FILE="${COMPOSE_FILE:-compose.production.yaml}"
: "${APP_ORIGIN:?Set the public HTTPS URL in your shell}"
if [[ "$APP_ORIGIN" != https://* ]]; then
  echo 'Refusing public HTTP origin for production.' >&2
  exit 1
fi
printf '%s\n' 'Checking running containers and backend health...'
docker compose -f "$COMPOSE_FILE" ps
printf '%s\n' 'Auditing database consistency (read only)...'
docker compose -f "$COMPOSE_FILE" exec -T backend python -m app.production_audit
printf '%s\n' 'Checking public health endpoint through TLS...'
curl --fail --show-error --silent --max-time 15 "$APP_ORIGIN/api/health"
printf '\nProduction checks completed. Review report warnings and manual launch checklist.\n'
