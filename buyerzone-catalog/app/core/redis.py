import asyncio
import json
import time

import redis.asyncio as aioredis
import structlog
from arq.connections import ArqRedis, create_pool

from app.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_redis: aioredis.Redis | None = None
_arq_pool: ArqRedis | None = None
_arq_lock = asyncio.Lock()

# ── Backpressure / rate-limit tunables ────────────────────────────────────────
# Drop new jobs if ARQ's pending queue exceeds this depth — prevents a dead
# worker from blowing up Redis memory under a sustained incoming load.
MAX_QUEUE_DEPTH = 10_000
# Per-chat sliding-window cap (fixed-window by wall-clock minute).
RATE_LIMIT_PER_CHAT_PER_MINUTE = 60
# ARQ's default sorted-set key for pending jobs. If you pass a custom
# `queue_name` to enqueue_job, mirror it here.
ARQ_QUEUE_KEY = "arq:queue"
# Dead-letter list for dropped messages — inspect with `LRANGE buyerzone:dlq 0 50`.
DLQ_KEY = "buyerzone:dlq"
DLQ_MAX_LEN = 10_000


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        import ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        _redis = aioredis.from_url(
            settings.redis_url_with_auth,
            encoding="utf-8",
            decode_responses=True,
            ssl=ctx,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


async def get_arq_pool() -> ArqRedis:
    """Lazy singleton — first call opens the pool, later calls reuse it."""
    global _arq_pool
    if _arq_pool is None:
        async with _arq_lock:
            if _arq_pool is None:
                _arq_pool = await create_pool(settings.arq_redis_settings)
    return _arq_pool


async def close_arq_pool() -> None:
    global _arq_pool
    if _arq_pool is not None:
        await _arq_pool.aclose()
        _arq_pool = None


# ── Backpressure helpers ──────────────────────────────────────────────────────

async def _check_rate_limit(redis, chat_id: int) -> int:
    """Increment per-chat per-minute counter. Returns post-increment count."""
    minute_bucket = int(time.time() // 60)
    key = f"buyerzone:ratelimit:{chat_id}:{minute_bucket}"
    count = await redis.incr(key)
    if count == 1:
        # 120s TTL gives a 60s grace window past the bucket — prevents ghost
        # keys from piling up if something goes wrong mid-minute.
        await redis.expire(key, 120)
    return count


async def _dlq_push(redis, payload: dict, *, reason: str, **extra) -> None:
    """Stash a dropped message's metadata (without the image blob) in the DLQ."""
    lite = {k: v for k, v in payload.items() if k != "image_b64"}
    lite["has_image"] = payload.get("has_image", payload.get("image_b64") is not None)
    entry = {"reason": reason, "ts": time.time(), "payload": lite, **extra}
    try:
        await redis.lpush(DLQ_KEY, json.dumps(entry, default=str))
        await redis.ltrim(DLQ_KEY, 0, DLQ_MAX_LEN - 1)
    except Exception as exc:
        log.error("dlq_push_failed", reason=reason, error=str(exc))


# ── ARQ job queue helper ──────────────────────────────────────────────────────

async def enqueue_message(payload: dict, *, bypass_limits: bool = False) -> None:
    """Enqueue a message for the ARQ worker.

    Drops (to DLQ + logs) if backpressure or per-chat rate limits are exceeded.
    Catch-up replay should pass bypass_limits=True so recovery doesn't get
    silently throttled.
    """
    pool = await get_arq_pool()
    chat_id = payload.get("chat_id")
    msg_id = payload.get("message_id")

    if not bypass_limits:
        if chat_id is not None:
            count = await _check_rate_limit(pool, chat_id)
            if count > RATE_LIMIT_PER_CHAT_PER_MINUTE:
                log.warning(
                    "enqueue_dropped",
                    reason="rate_limited",
                    chat_id=chat_id,
                    msg_id=msg_id,
                    count_this_minute=count,
                )
                await _dlq_push(pool, payload, reason="rate_limited", count=count)
                return

        depth = await pool.zcard(ARQ_QUEUE_KEY)
        if depth >= MAX_QUEUE_DEPTH:
            log.warning(
                "enqueue_dropped",
                reason="queue_full",
                chat_id=chat_id,
                msg_id=msg_id,
                queue_depth=depth,
            )
            await _dlq_push(pool, payload, reason="queue_full", queue_depth=depth)
            return

    await pool.enqueue_job("process_message", payload)
