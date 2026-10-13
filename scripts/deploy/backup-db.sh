#!/usr/bin/env bash
# Daily logical backup of the production database, kept for KEEP_DAYS days.
# The files sit on the EBS volume, so the daily EBS snapshot carries them too.
#
# crontab on the EC2 host (03:00 server time):
#   0 3 * * * /opt/grant-radar/scripts/deploy/backup-db.sh >> /var/log/grant-radar-backup.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/../.."

KEEP_DAYS="${KEEP_DAYS:-7}"
mkdir -p backups
out="backups/web3agent_$(date +%Y%m%d_%H%M%S).sql.gz"
trap 'rm -f "$out.tmp"' EXIT

# The postgres container already has POSTGRES_USER / POSTGRES_DB in its environment.
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' | gzip > "$out.tmp"
mv "$out.tmp" "$out"
find backups -name 'web3agent_*.sql.gz' -mtime +"$KEEP_DAYS" -delete

echo "$(date -Is) wrote $out ($(du -h "$out" | cut -f1))"
