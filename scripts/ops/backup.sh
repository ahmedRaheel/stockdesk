#!/usr/bin/env bash
# Consistent PostgreSQL logical backup. Provide DATABASE_URL via secure env or PG* vars.
set -Eeuo pipefail
umask 077
: "${DATABASE_URL:?DATABASE_URL is required}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p -- "$BACKUP_DIR"
command -v pg_dump >/dev/null || { echo 'pg_dump is required' >&2; exit 1; }
command -v pg_restore >/dev/null || { echo 'pg_restore is required' >&2; exit 1; }
command -v sha256sum >/dev/null || { echo 'sha256sum is required' >&2; exit 1; }
filename="stockdesk-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
tmp="$BACKUP_DIR/.${filename}.partial"
trap 'rm -f -- "$tmp"' EXIT
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-acl --file="$tmp"
# Validate archive TOC before marking as complete. This does not prove restorability.
pg_restore --list "$tmp" >/dev/null
mv -- "$tmp" "$BACKUP_DIR/$filename"
sha256sum "$BACKUP_DIR/$filename" > "$BACKUP_DIR/$filename.sha256"
trap - EXIT
printf 'Backup created: %s\n' "$BACKUP_DIR/$filename"
echo 'Important: copy backup and checksum off host with encryption and restricted access.'
