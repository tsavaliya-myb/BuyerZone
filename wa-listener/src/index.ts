/**
 * Entry point — loads auth state from FastAPI, starts Baileys, serves internal HTTP API.
 */

import "dotenv/config";
import { config } from "./config.js";
import { log } from "./logger.js";
import { startBot, resetBot } from "./listener.js";
import { reloadWhitelistFromDB } from "./whitelist.js";
import { createApp } from "./http.js";
import { closeRedis } from "./queue.js";

async function main(): Promise<void> {
  log.info({ port: config.port }, "wa_listener_starting");

  // ── Load auth state from FastAPI / PostgreSQL ──────────────────────────────
  let serialisedAuth: Record<string, unknown> | null = null;
  try {
    const resp = await fetch(
      `${config.fastapiUrl}/api/v1/internal/whatsapp/session`,
      { headers: { "X-Internal-Key": config.internalSecret } }
    );
    if (resp.ok) {
      const data = await resp.json() as { auth_state?: Record<string, unknown> };
      serialisedAuth = data.auth_state ?? null;
      log.info("wa_session_loaded_from_db");
    } else {
      log.info({ status: resp.status }, "wa_session_not_found_starting_fresh");
    }
  } catch (err) {
    log.warn({ err }, "wa_session_load_error_starting_fresh");
  }

  // ── Start Baileys ──────────────────────────────────────────────────────────
  await startBot(serialisedAuth);

  // ── Load whitelist ─────────────────────────────────────────────────────────
  await reloadWhitelistFromDB(config.fastapiUrl, config.internalSecret);

  // ── Start internal HTTP server ─────────────────────────────────────────────
  const app = createApp();
  const server = app.listen(config.port, "0.0.0.0", () => {
    log.info({ port: config.port }, "wa_internal_http_ready");
  });

  // ── Graceful shutdown ──────────────────────────────────────────────────────
  const shutdown = async (signal: string) => {
    log.info({ signal }, "shutting_down");
    server.close();
    await closeRedis();
    process.exit(0);
  };

  process.on("SIGTERM", () => shutdown("SIGTERM"));
  process.on("SIGINT", () => shutdown("SIGINT"));
}

main().catch((err) => {
  console.error("Fatal error in wa-listener:", err);
  process.exit(1);
});
