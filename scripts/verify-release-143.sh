#!/usr/bin/env bash
# Developer/release checks. Does not mutate the database.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m compileall -q backend/app
(
  cd backend
  python -m pytest -q tests/test_release_143.py tests/test_release_143_contract.py
)
(
  cd frontend
  node --test scripts/request-id.test.cjs scripts/csv.test.cjs
  if [[ -d node_modules ]]; then npm run build; else echo "WARNING: npm dependencies are not installed; React build skipped"; fi
)
echo "Static and focused checks finished; run database and browser staging tests separately."
