/**
 * Queue bridge — POSTs MessagePayload to the FastAPI /internal/whatsapp/enqueue
 * endpoint, which uses ARQ's native enqueue_job (sorted set + msgpack).
 * Direct Redis writes used an incompatible format and are replaced by this.
 */

import { config } from "./config.js";
import type { MessagePayload } from "./payload.js";

export async function enqueuePayload(payload: MessagePayload): Promise<void> {
  const url = `${config.fastapiUrl}/api/v1/internal/whatsapp/enqueue`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Key": config.internalSecret,
    },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new Error(`enqueue HTTP ${resp.status}: ${text}`);
  }
}

// No-op — no persistent connection to close
export async function closeRedis(): Promise<void> {}
