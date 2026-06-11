/**
 * Baileys client — authentication state machine + message handler.
 *
 * States: awaiting_pair_code → pair_pending → connected → disconnected / requires_repair
 */

import {
  Browsers,
  DisconnectReason,
  WAMessage,
  fetchLatestWaWebVersion,
  makeWASocket,
  proto,
} from "baileys";
import { Boom } from "@hapi/boom";
import { baileysLogger, log } from "./logger.js";
import { loadAuthState, persistAuthState, serialiseAuthState } from "./auth.js";
import { isMonitored, getWhitelist } from "./whitelist.js";
import { downloadAndEncode } from "./downloader.js";
import { buildPayload } from "./payload.js";
import { enqueuePayload } from "./queue.js";
import { config } from "./config.js";

export type ListenerState =
  | "awaiting_pair_code"
  | "pair_pending"
  | "connected"
  | "disconnected"
  | "requires_repair";

interface ListenerContext {
  state: ListenerState;
  phone: string | null;
  displayName: string | null;
  sock: ReturnType<typeof makeWASocket> | null;
  pairCode: string | null;
}

const ctx: ListenerContext = {
  state: "awaiting_pair_code",
  phone: null,
  displayName: null,
  sock: null,
  pairCode: null,
};

/** Consecutive reconnect attempts — drives exponential backoff. */
let reconnectAttempts = 0;

/**
 * After this many consecutive failures we give up and move to requires_repair
 * rather than retrying forever with a likely-dead session (e.g. persistent 408).
 */
const MAX_RECONNECT_ATTEMPTS = 10;

export function getState(): ListenerState {
  return ctx.state;
}

export function getPhone(): string | null {
  return ctx.phone;
}

export function getDisplayName(): string | null {
  return ctx.displayName;
}

// Out-of-stock signal patterns (case-insensitive)
const OOS_RE = /out\s+of\s+stock|stock\s+out|not\s+available|sold\s+out/i;

/**
 * Start (or restart) the Baileys socket with the current auth state.
 * Pass serialisedAuth=null for a first-time (unpaired) session.
 */
export async function startBot(
  serialisedAuth: Record<string, unknown> | null,
  phone?: string
): Promise<void> {
  if (phone) ctx.phone = phone;

  const authState = loadAuthState(serialisedAuth);
  // Try the live WA Web version first (fetched from web.whatsapp.com) — when
  // WA bumps the server protocol, the previously pinned version starts timing
  // out the handshake at 408. Fall back to the known-good pin if the fetch
  // fails or the network blocks it.
  const fallbackVersion: [number, number, number] = [2, 3000, 1035194821];
  let version: [number, number, number] = fallbackVersion;
  try {
    const fetched = await fetchLatestWaWebVersion({});
    if (fetched?.version) {
      version = fetched.version as [number, number, number];
    }
  } catch (err) {
    log.warn({ err }, "wa_version_fetch_failed_using_fallback");
  }
  log.info({ version }, "baileys_version");

  const sock = makeWASocket({
    version,
    browser: Browsers.ubuntu("Chrome"),
    auth: authState,
    logger: baileysLogger,
    printQRInTerminal: false,
    markOnlineOnConnect: false,
    syncFullHistory: false,
  });
  ctx.sock = sock;

  // ── Credential updates ────────────────────────────────────────────────────
  sock.ev.on("creds.update", async () => {
    const phone = ctx.phone ?? "unknown";
    const displayName = ctx.displayName ?? undefined;
    await persistAuthState(phone, displayName);
  });

  // ── Connection state ──────────────────────────────────────────────────────
  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (connection === "open") {
      ctx.state = "connected";
      ctx.displayName = sock.user?.name ?? null;
      ctx.phone = sock.user?.id?.split(":")[0] ?? ctx.phone;
      reconnectAttempts = 0;
      log.info({ phone: ctx.phone, displayName: ctx.displayName }, "wa_connected");
      // Newsletter (channel) messages only stream after subscribing to live
      // updates. Re-subscribe every monitored newsletter on connect.
      void resubscribeAllNewsletters();
    }

    if (connection === "close") {
      const err = lastDisconnect?.error as Boom | undefined;
      const code = err?.output?.statusCode;

      if (code === DisconnectReason.loggedOut || code === 405) {
        // Permanent — do not auto-reconnect
        ctx.state = "requires_repair";
        ctx.sock = null;
        reconnectAttempts = 0;
        log.warn({ code }, "wa_requires_repair");
      } else if (code === 440) {
        // 440 = Connection Replaced — another session with the same
        // credentials is active (duplicate container, browser WA Web open,
        // etc.).  Auto-reconnecting creates an infinite kick-loop.
        // Stop and surface to admin.
        ctx.state = "requires_repair";
        ctx.sock = null;
        reconnectAttempts = 0;
        log.warn(
          { code },
          "wa_connection_replaced — another active session detected. " +
          "Close other WA Web sessions or stop duplicate containers, then re-pair."
        );
      } else if (ctx.state === "pair_pending" && code !== 515) {
        // Unexpected disconnect while a pairing code is pending (not the normal
        // 515 "restart required" that WA sends after the user enters the code).
        // The code is now dead — restart fresh so the admin can request a new one.
        ctx.state = "awaiting_pair_code";
        ctx.sock = null;
        reconnectAttempts = 0;
        log.warn({ code }, "wa_pair_interrupted_restarting");
        setTimeout(() => startBot(null), 3000);
      } else {
        // Transient — reconnect with exponential backoff.
        // 515 (restartRequired) is WA's normal ack after code entry; reconnecting
        // with the current auth state completes the pairing handshake.
        reconnectAttempts++;

        if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
          // Too many consecutive failures — the session is likely dead/revoked.
          // Stop retrying and surface for admin intervention instead of looping
          // forever (e.g. persistent 408 with a stale DB session).
          ctx.state = "requires_repair";
          ctx.sock = null;
          log.warn(
            { code, attempt: reconnectAttempts },
            "wa_max_reconnects_exceeded — session appears dead. Re-pair via admin panel."
          );
          return;
        }

        ctx.state = "disconnected";
        const backoffMs = Math.min(3000 * Math.pow(2, reconnectAttempts - 1), 60000);
        log.info({ code, attempt: reconnectAttempts, backoffMs }, "wa_reconnecting");
        const current = serialiseAuthState();
        setTimeout(() => startBot(current, ctx.phone ?? undefined), backoffMs);
      }
    }
  });

  // ── Incoming messages ─────────────────────────────────────────────────────
  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    // Skip history sync batches
    if (type !== "notify" && type !== "append") return;

    for (const msg of messages) {
      await handleMessage(msg);
    }
  });
}

// ── Newsletter live-updates subscription ─────────────────────────────────────
// Newsletters (WA Channels) only push messages while a live-updates
// subscription is active. The server returns a `duration` (seconds); we must
// re-subscribe before it expires, otherwise messages stop flowing.

const newsletterTimers = new Map<string, NodeJS.Timeout>();

export async function subscribeNewsletter(jid: string): Promise<void> {
  if (!ctx.sock) return;
  if (!jid.endsWith("@newsletter")) return;
  try {
    // Follow is idempotent — ensures account is following the channel.
    try {
      await (ctx.sock as any).newsletterFollow(jid);
    } catch (err) {
      log.debug({ err, jid }, "newsletter_follow_skipped");
    }
    const result = await (ctx.sock as any).subscribeNewsletterUpdates(jid);
    const duration =
      typeof result?.duration === "string"
        ? parseInt(result.duration, 10)
        : result?.duration ?? 0;
    log.info({ jid, duration }, "newsletter_subscribed");

    // Schedule refresh ~30s before expiry (default to 5 min if duration unknown).
    const refreshSec = duration > 60 ? duration - 30 : 300;
    const existing = newsletterTimers.get(jid);
    if (existing) clearTimeout(existing);
    const timer = setTimeout(() => {
      newsletterTimers.delete(jid);
      void subscribeNewsletter(jid);
    }, refreshSec * 1000);
    timer.unref?.();
    newsletterTimers.set(jid, timer);
  } catch (err) {
    log.warn({ err, jid }, "newsletter_subscribe_failed");
  }
}

export async function resubscribeAllNewsletters(): Promise<void> {
  for (const timer of newsletterTimers.values()) clearTimeout(timer);
  newsletterTimers.clear();
  for (const jid of getWhitelist().keys()) {
    if (jid.endsWith("@newsletter")) {
      await subscribeNewsletter(jid);
    }
  }
}

/**
 * Request a pairing code for the given phone number.
 * The socket must already be initialised (call startBot first).
 */
export async function requestPairingCode(phone: string): Promise<string> {
  if (!ctx.sock) throw new Error("Socket not initialised");
  ctx.phone = phone;
  ctx.state = "pair_pending";
  const code = await ctx.sock.requestPairingCode(phone);
  ctx.pairCode = code;
  log.info({ phone, code }, "pairing_code_requested");
  return code;
}

/**
 * Wipe in-memory state and reinitialise with an empty auth state.
 * Called after the admin clicks "Re-pair" to clear a revoked session.
 */
export async function resetBot(): Promise<void> {
  if (ctx.sock) {
    try {
      await ctx.sock.logout();
    } catch {
      // ignore — socket may already be dead
    }
    ctx.sock = null;
  }
  ctx.state = "awaiting_pair_code";
  ctx.phone = null;
  ctx.displayName = null;
  ctx.pairCode = null;
  await startBot(null);
}

// ---------------------------------------------------------------------------

async function handleMessage(msg: WAMessage): Promise<void> {
  // FILTER 1: guard key, skip own messages
  if (!msg.key) return;
  if (msg.key.fromMe) return;

  const jid = msg.key.remoteJid;
  if (!jid) return;

  // FILTER 2: whitelist
  if (!isMonitored(jid)) return;

  // FILTER 3: unwrap message envelope
  const imageMsg = extractImageMessage(msg);
  if (!imageMsg) return;

  // FILTER 4: out-of-stock caption
  const caption = imageMsg.caption ?? "";
  if (OOS_RE.test(caption)) {
    log.info({ jid, msgId: msg.key.id }, "skipped_oos");
    return;
  }

  // DOWNLOAD + encode
  const b64 = await downloadAndEncode(msg, imageMsg);
  if (!b64) return;

  // BUILD payload
  const payload = buildPayload(msg, caption, b64);

  // ENQUEUE
  try {
    await enqueuePayload(payload);
    log.info({ jid, msgId: msg.key.id }, "message_enqueued");
  } catch (err) {
    log.error({ err, jid, msgId: msg.key.id }, "enqueue_failed");
  }
}

/**
 * Peel wrapping layers from a message envelope and return the first
 * imageMessage found. Returns null if no image is present.
 * Only the first image in multi-image messages is used (per spec §5.3).
 */
function extractImageMessage(
  msg: WAMessage
): proto.Message.IImageMessage | null {
  const wrappers = [
    "ephemeralMessage",
    "viewOnceMessage",
    "viewOnceMessageV2",
    "viewOnceMessageV2Extension",
    "documentWithCaptionMessage",
    "editedMessage",
  ] as const;

  let content: proto.IMessage = msg.message ?? {};

  for (const key of wrappers) {
    const wrapped = (content as any)[key]?.message;
    if (wrapped) {
      content = wrapped;
      break;
    }
  }

  if (content.imageMessage) return content.imageMessage;

  // Quoted image in a text reply
  const quoted = content.extendedTextMessage?.contextInfo?.quotedMessage;
  if (quoted?.imageMessage) return quoted.imageMessage;

  return null;
}

/** Expose the live sock for admin introspection (joined groups, etc.) */
export function getSock(): ReturnType<typeof makeWASocket> | null {
  return ctx.sock;
}
