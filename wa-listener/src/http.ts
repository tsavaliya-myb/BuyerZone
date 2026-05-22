/**
 * Internal HTTP API — consumed only by FastAPI. Bound to container network only.
 * All routes require the X-Internal-Secret header.
 */

import express, { NextFunction, Request, Response } from "express";
import { config } from "./config.js";
import { log } from "./logger.js";
import {
  getState,
  getPhone,
  getDisplayName,
  getSock,
  requestPairingCode,
  resetBot,
  startBot,
  subscribeNewsletter,
  resubscribeAllNewsletters,
} from "./listener.js";
import {
  reloadWhitelistFromDB,
  setWhitelist,
  getWhitelist,
} from "./whitelist.js";

export function createApp(): express.Application {
  const app = express();
  app.use(express.json());

  // ── Auth middleware ─────────────────────────────────────────────────────────
  app.use((req: Request, res: Response, next: NextFunction) => {
    const secret = req.headers["x-internal-secret"];
    if (secret !== config.internalSecret) {
      res.status(403).json({ error: "forbidden" });
      return;
    }
    next();
  });

  // ── Status ──────────────────────────────────────────────────────────────────
  app.get("/wa-internal/status", (_req: Request, res: Response) => {
    res.json({
      state: getState(),
      phone: getPhone(),
      display_name: getDisplayName(),
    });
  });

  // ── Pairing ─────────────────────────────────────────────────────────────────
  app.post("/wa-internal/pair", async (req: Request, res: Response) => {
    const { phone } = req.body as { phone?: string };
    if (!phone) {
      res.status(400).json({ error: "phone required" });
      return;
    }
    try {
      // Always reset to a fresh socket before pairing to avoid stale-session
      // conflicts that cause WA to reject the code with 401.
      const state = getState();
      if (state !== "awaiting_pair_code") {
        log.info({ state }, "pair_auto_reset");
        await resetBot();
        await new Promise((r) => setTimeout(r, 2000));
      }
      const code = await requestPairingCode(phone);
      res.json({ code, expires_in: 60 });
    } catch (err: any) {
      log.error({ err }, "pair_error");
      res.status(500).json({ error: err?.message ?? "pair_failed" });
    }
  });

  app.post("/wa-internal/reset", async (_req: Request, res: Response) => {
    try {
      await resetBot();
      res.json({ status: "reset" });
    } catch (err: any) {
      log.error({ err }, "reset_error");
      res.status(500).json({ error: err?.message ?? "reset_failed" });
    }
  });

  // ── Whitelist ────────────────────────────────────────────────────────────────
  app.post("/wa-internal/whitelist/reload", async (_req: Request, res: Response) => {
    await reloadWhitelistFromDB(config.fastapiUrl, config.internalSecret);
    // Refresh newsletter live-updates subscriptions for any (re)added channels.
    void resubscribeAllNewsletters();
    res.json({ status: "ok", count: getWhitelist().size });
  });

  // ── Joined chats ────────────────────────────────────────────────────────────
  app.get("/wa-internal/joined", async (req: Request, res: Response) => {
    const sock = getSock();
    if (!sock) {
      res.status(503).json({ error: "not_connected" });
      return;
    }

    const q = ((req.query.q as string) ?? "").toLowerCase();

    try {
      // Race against a timeout — if Baileys hangs (broken/disconnected session),
      // we must still send a response or the caller gets a RemoteProtocolError.
      const TIMEOUT_MS = 12_000;
      const groups = await Promise.race([
        sock.groupFetchAllParticipating(),
        new Promise<never>((_, reject) =>
          setTimeout(() => reject(new Error("groupFetch timed out")), TIMEOUT_MS)
        ),
      ]);

      const monitored = getWhitelist();

      const results = Object.values(groups)
        .filter((g: any) => !q || g.subject?.toLowerCase().includes(q))
        .map((g: any) => ({
          jid: g.id,
          name: g.subject,
          type: "wa_group",
          participant_count: g.participants?.length ?? null,
          is_community_parent: g.isCommunity ?? false,
          is_community_subgroup: g.isCommunityAnnounce === false && g.linkedParent != null,
          already_monitored: monitored.has(g.id),
        }));

      res.json(results);
    } catch (err: any) {
      log.error({ err }, "joined_groups_error");
      const isTimeout = err?.message?.includes("timed out");
      res
        .status(isTimeout ? 504 : 500)
        .json({ error: err?.message ?? "fetch_failed" });
    }
  });

  // ── Resolve invite link ─────────────────────────────────────────────────────
  app.post("/wa-internal/resolve-link", async (req: Request, res: Response) => {
    const sock = getSock();
    if (!sock) {
      res.status(503).json({ error: "not_connected" });
      return;
    }

    const { url, code: rawCode } = req.body as { url?: string; code?: string };
    if (!url && !rawCode) {
      res.status(400).json({ error: "url or code required" });
      return;
    }

    // Accept bare channel code (e.g. "0025588484844") or full URL
    const resolvedUrl = rawCode
      ? `https://whatsapp.com/channel/${rawCode.trim()}`
      : url!;

    try {
      let jid: string;
      let name: string;
      let chatType: string;

      if (resolvedUrl.includes("whatsapp.com/channel/")) {
        // WhatsApp Channel (Newsletter)
        const code = resolvedUrl.split("/").pop()!;
        const meta = await (sock as any).newsletterMetadata("invite", code);
        jid = meta.id;
        name =
          meta.thread_metadata?.name?.text ??
          meta.threadMetadata?.name?.text ??
          meta.name ??
          meta.subject ??
          jid;
        chatType = "wa_channel";
      } else {
        // Group or community
        const code = resolvedUrl.split("/").pop()!;
        const info = await sock.groupGetInviteInfo(code);
        jid = info.id;
        name = info.subject;
        chatType = "wa_group";
      }

      // Membership check
      const monitored = getWhitelist();
      let isMember = false;
      if (chatType === "wa_group") {
        const groups = await sock.groupFetchAllParticipating();
        isMember = jid in groups;
      } else {
        // For channels, assume joined if we can resolve the metadata
        isMember = true;
      }

      if (!isMember) {
        res.status(409).json({
          error: "not_joined",
          message: `Resolved '${name}' but the bot account is not a member. Join on the linked phone first.`,
          preview: { jid, name, type: chatType },
        });
        return;
      }

      res.json({
        jid,
        name,
        type: chatType,
        already_monitored: monitored.has(jid),
        is_member: true,
      });
    } catch (err: any) {
      log.error({ err, url }, "resolve_link_error");
      res.status(500).json({ error: err?.message ?? "resolve_failed" });
    }
  });

  // ── Subscribe newsletter live updates ───────────────────────────────────────
  app.post("/wa-internal/subscribe-newsletter", async (req: Request, res: Response) => {
    const sock = getSock();
    if (!sock) {
      res.status(503).json({ error: "not_connected" });
      return;
    }
    const { jid } = req.body as { jid?: string };
    if (!jid) {
      res.status(400).json({ error: "jid required" });
      return;
    }
    try {
      await subscribeNewsletter(jid);
      res.json({ status: "subscribed" });
    } catch (err: any) {
      log.warn({ err, jid }, "subscribe_newsletter_warn");
      res.json({ status: "ok" }); // non-fatal
    }
  });

  return app;
}
