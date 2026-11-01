#!/usr/bin/env bash
# Destructive to the TARGET database: restore ONLY into an isolated, disposable database.
set -Eeuo pipefail
umask 077
: "${BACKUP_FILE:?Specify the backup archive}"
: "${RESTORE_DATABASE_URL:?Specify a disposable restore target}"
: "${RESTORE_CONFIRM:?Set RESTORE_CONFIRM=DISPOSABLE_DATABASE_ONLY}"
if [[ "$RESTORE_CONFIRM" != DISPOSABLE_DATABASE_ONLY ]]; then
  echo 'Restore confirmation missing.' >&2; exit 1
fi
[[ -f "$BACKUP_FILE" && -f "$BACKUP_FILE.sha256" ]] || { echo 'Archive/checksum not found' >&2; exit 1; }
(cd "$(dirname "$BACKUP_FILE")" && sha256sum --check "$(basename "$BACKUP_FILE").sha256")
command -v pg_restore >/dev/null || exit 1
command -v psql >/dev/null || exit 1
# Refuse likely production destinations even if a user provides the confirmation.
if [[ "$RESTORE_DATABASE_URL" == "$DATABASE_URL" && -n "${DATABASE_URL:-}" ]]; then
  echo 'Refusing to restore into source DATABASE_URL.' >&2; exit 1
fi
if [[ "$RESTORE_DATABASE_URL" != *stockdesk_restore_test* ]]; then
  echo 'Target database name must contain stockdesk_restore_test.' >&2; exit 1
fi
# Require empty database; prevents accidental replacement of any existing data.
existing="$(psql "$RESTORE_DATABASE_URL" -AtX -c "SELECT COUNT(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m')")"
if [[ "$existing" != 0 ]]; then echo 'Target is not empty; refusing restore.' >&2; exit 1; fi
pg_restore --dbname="$RESTORE_DATABASE_URL" --no-owner --no-acl --single-transaction --exit-on-error "$BACKUP_FILE"
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -AtX -c 'SELECT COUNT(*) FROM schema_migrations;'
psql "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -AtX -c 'SELECT COUNT(*) FROM tenants;'
echo 'Restore rehearsal passed. Keep this target isolated and destroy it securely.'
