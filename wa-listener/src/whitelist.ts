/**
 * In-memory whitelist of monitored JIDs.
 * Loaded from PostgreSQL at startup and refreshed on /wa-internal/whitelist/reload.
 * Maps jid → chat_name for use in MessagePayload.
 */

import { log } from "./logger.js";

const _whitelist = new Map<string, string>(); // jid → chat_name

export function isMonitored(jid: string): boolean {
  return _whitelist.has(jid);
}

export function getChatName(jid: string): string {
  return _whitelist.get(jid) ?? jid;
}

export function getWhitelist(): Map<string, string> {
  return new Map(_whitelist);
}

export function setWhitelist(entries: Array<{ jid: string; name: string }>): void {
  _whitelist.clear();
  for (const { jid, name } of entries) {
    _whitelist.set(jid, name);
  }
  log.info({ count: _whitelist.size }, "whitelist_loaded");
}

/**
 * Reload the whitelist from FastAPI (which reads from PostgreSQL).
 */
export async function reloadWhitelistFromDB(fastapiUrl: string, secret: string): Promise<void> {
  try {
    const resp = await fetch(`${fastapiUrl}/api/v1/internal/whatsapp/monitored-chats`, {
      headers: { "X-Internal-Key": secret },
    });
    if (!resp.ok) {
      log.warn({ status: resp.status }, "whitelist_reload_http_error");
      return;
    }
    const chats: Array<{ chat_id: string; chat_name: string }> = await resp.json();
    setWhitelist(chats.map((c) => ({ jid: c.chat_id, name: c.chat_name })));
  } catch (err) {
    log.warn({ err }, "whitelist_reload_error");
  }
}
