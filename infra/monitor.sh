#!/usr/bin/env bash
# Health monitor — checks API liveness + ARQ dead-letter queue depth
# Schedule: */5 * * * * /home/deploy/apps/BuyerZone/infra/monitor.sh
#
# Required env vars (add to /home/deploy/.env.monitor or export in crontab):
#   DISCORD_WEBHOOK_URL   — Discord webhook for alerts
#   REDIS_PASSWORD        — to query ARQ queues
#   DLQ_ALERT_THRESHOLD   — alert if DLQ depth exceeds this (default: 10)

set -euo pipefail

DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL:-}"
REDIS_PASSWORD="${REDIS_PASSWORD:-}"
DLQ_THRESHOLD="${DLQ_ALERT_THRESHOLD:-10}"
API_URL="http://localhost:8000/health"
STATE_DIR="/tmp/bz-monitor"

mkdir -p "$STATE_DIR"

# ── Helper: send Discord alert ───────────────────────────────────────────────
alert() {
  local msg="$1"
  echo "[ALERT] $msg"
  if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    curl -sf -X POST "$DISCORD_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"content\": \"🚨 **BuyerZone Alert** — ${msg}\"}" \
      > /dev/null || true
  fi
}

recover() {
  local msg="$1"
  echo "[RECOVER] $msg"
  if [ -n "$DISCORD_WEBHOOK_URL" ]; then
    curl -sf -X POST "$DISCORD_WEBHOOK_URL" \
      -H "Content-Type: application/json" \
      -d "{\"content\": \"✅ **BuyerZone Recovered** — ${msg}\"}" \
      > /dev/null || true
  fi
}

# ── Check 1: API health ──────────────────────────────────────────────────────
API_STATE_FILE="$STATE_DIR/api_down"

if curl -sf --max-time 5 "$API_URL" > /dev/null 2>&1; then
  if [ -f "$API_STATE_FILE" ]; then
    rm "$API_STATE_FILE"
    recover "API is back up at $API_URL"
  fi
else
  if [ ! -f "$API_STATE_FILE" ]; then
    touch "$API_STATE_FILE"
    alert "API health check failed — $API_URL is not responding"
  fi
fi

# ── Check 2: ARQ dead-letter queue depth ─────────────────────────────────────
if [ -n "$REDIS_PASSWORD" ]; then
  DLQ_DEPTH=$(docker exec \
    $(docker ps -qf name=redis 2>/dev/null | head -1) \
    redis-cli -a "$REDIS_PASSWORD" --no-auth-warning \
    LLEN "arq:queue:process_message:dead" 2>/dev/null || echo "0")

  DLQ_STATE_FILE="$STATE_DIR/dlq_alerted"

  if [ "$DLQ_DEPTH" -gt "$DLQ_THRESHOLD" ] 2>/dev/null; then
    if [ ! -f "$DLQ_STATE_FILE" ]; then
      touch "$DLQ_STATE_FILE"
      alert "ARQ dead-letter queue has ${DLQ_DEPTH} failed jobs (threshold: ${DLQ_THRESHOLD})"
    fi
  else
    if [ -f "$DLQ_STATE_FILE" ]; then
      rm "$DLQ_STATE_FILE"
      recover "ARQ dead-letter queue cleared (now ${DLQ_DEPTH} jobs)"
    fi
  fi
fi

# ── Check 3: Disk usage ──────────────────────────────────────────────────────
DISK_PCT=$(df / | awk 'NR==2 {gsub(/%/,""); print $5}')
DISK_STATE_FILE="$STATE_DIR/disk_alerted"

if [ "$DISK_PCT" -gt 85 ]; then
  if [ ! -f "$DISK_STATE_FILE" ]; then
    touch "$DISK_STATE_FILE"
    alert "Disk usage at ${DISK_PCT}% — clean up logs or Docker images"
  fi
else
  [ -f "$DISK_STATE_FILE" ] && rm "$DISK_STATE_FILE" || true
fi
