#!/usr/bin/env bash
# Nightly backup — Postgres dump + Docker volumes snapshot to Cloudflare R2
# Schedule: 0 2 * * * /home/deploy/apps/BuyerZone/infra/backup.sh >> /var/log/bz-backup.log 2>&1

set -euo pipefail

COMPOSE="docker compose -f /home/deploy/apps/BuyerZone/infra/docker-compose.prod.yml"
BACKUP_DIR="/home/deploy/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

echo "=== BuyerZone Backup — $DATE ==="

# ── Postgres dump ────────────────────────────────────────────────────────────
echo "[1/3] Postgres dump..."
$COMPOSE exec -T postgres \
  pg_dump -U buyerzone buyerzone \
  | gzip > "$BACKUP_DIR/postgres_${DATE}.sql.gz"
echo "      Done: postgres_${DATE}.sql.gz"

# ── Qdrant snapshot ──────────────────────────────────────────────────────────
echo "[2/3] Qdrant snapshot..."
curl -sf -X POST "http://localhost:6333/collections/product_embeddings/snapshots" \
  -o /dev/null
# Wait for snapshot to complete then copy from volume
sleep 5
SNAP=$(docker run --rm \
  -v buyerzone_qdrant_data:/data alpine \
  ls /data/snapshots/product_embeddings/ 2>/dev/null | tail -1)
if [ -n "$SNAP" ]; then
  docker run --rm \
    -v buyerzone_qdrant_data:/data \
    -v "$BACKUP_DIR":/out alpine \
    cp "/data/snapshots/product_embeddings/$SNAP" "/out/qdrant_${DATE}.snapshot"
  echo "      Done: qdrant_${DATE}.snapshot"
else
  echo "      Warning: no Qdrant snapshot found — skipping"
fi

# ── WhatsApp session backup ──────────────────────────────────────────────────
echo "[3/3] WA session backup..."
docker run --rm \
  -v buyerzone_wa_sessions:/data \
  -v "$BACKUP_DIR":/out alpine \
  sh -c "cd /data && tar czf /out/wa_sessions_${DATE}.tar.gz ." 2>/dev/null || \
  echo "      Warning: wa_sessions volume empty or missing — skipping"

# ── Upload to R2 ─────────────────────────────────────────────────────────────
if command -v aws &>/dev/null; then
  echo "Uploading to R2..."
  AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  aws s3 cp "$BACKUP_DIR/postgres_${DATE}.sql.gz" \
    "s3://${R2_BUCKET_NAME}/backups/postgres_${DATE}.sql.gz" \
    --endpoint-url "$R2_ENDPOINT_URL" --quiet
  echo "      Uploaded postgres dump"

  [ -f "$BACKUP_DIR/qdrant_${DATE}.snapshot" ] && \
  AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  aws s3 cp "$BACKUP_DIR/qdrant_${DATE}.snapshot" \
    "s3://${R2_BUCKET_NAME}/backups/qdrant_${DATE}.snapshot" \
    --endpoint-url "$R2_ENDPOINT_URL" --quiet && \
  echo "      Uploaded Qdrant snapshot"

  [ -f "$BACKUP_DIR/wa_sessions_${DATE}.tar.gz" ] && \
  AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  aws s3 cp "$BACKUP_DIR/wa_sessions_${DATE}.tar.gz" \
    "s3://${R2_BUCKET_NAME}/backups/wa_sessions_${DATE}.tar.gz" \
    --endpoint-url "$R2_ENDPOINT_URL" --quiet && \
  echo "      Uploaded WA sessions"
else
  echo "      aws CLI not found — skipping R2 upload (local backup only)"
fi

# ── Prune old local backups ──────────────────────────────────────────────────
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.snapshot" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "wa_sessions_*.tar.gz" -mtime +$RETENTION_DAYS -delete
echo "Pruned backups older than ${RETENTION_DAYS} days"

echo "=== Backup complete ==="
