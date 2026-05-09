/**
 * Auth state management — stores Baileys creds in FastAPI (PostgreSQL)
 * rather than on disk. On every creds.update the full state is POSTed to
 * /api/v1/admin/whatsapp/internal/session-update.
 */

import { AuthenticationState, initAuthCreds, BufferJSON, proto } from "baileys";
import { config } from "./config.js";
import { log } from "./logger.js";

// In-memory copy of the current auth state; persisted to DB on every update.
let _authState: AuthenticationState | null = null;

/**
 * Load auth state that was fetched from DB at startup.
 * Pass null to start a fresh (unpaired) session.
 */
export function loadAuthState(
  serialised: Record<string, unknown> | null
): AuthenticationState {
  if (!serialised) {
    const creds = initAuthCreds();
    _authState = {
      creds,
      keys: makeInMemoryKeys({}),
    };
    return _authState;
  }

  // Revive Buffer values serialised by BufferJSON.replacer
  const creds = JSON.parse(JSON.stringify(serialised.creds), BufferJSON.reviver);
  const rawKeys = JSON.parse(
    JSON.stringify(serialised.keys ?? {}),
    BufferJSON.reviver
  );
  _authState = {
    creds,
    keys: makeInMemoryKeys(rawKeys),
  };
  return _authState;
}

/**
 * Serialise the current in-memory auth state to a plain JSON object
 * suitable for JSONB storage and transmission.
 */
export function serialiseAuthState(): Record<string, unknown> {
  if (!_authState) throw new Error("Auth state not initialised");
  return JSON.parse(
    JSON.stringify(
      { creds: _authState.creds, keys: (_authState.keys as any)._data ?? {} },
      BufferJSON.replacer
    )
  );
}

/**
 * Persist the latest auth state back to FastAPI / PostgreSQL.
 * Called on every Baileys creds.update event.
 */
export async function persistAuthState(phone: string, displayName?: string): Promise<void> {
  try {
    const authState = serialiseAuthState();
    const resp = await fetch(
      `${config.fastapiUrl}/api/v1/admin/whatsapp/internal/session-update`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Internal-Secret": config.internalSecret,
        },
        body: JSON.stringify({
          auth_state: authState,
          phone,
          display_name: displayName ?? null,
        }),
      }
    );
    if (!resp.ok) {
      const text = await resp.text();
      log.warn({ status: resp.status, body: text }, "wa_session_persist_failed");
    }
  } catch (err) {
    log.warn({ err }, "wa_session_persist_error");
  }
}

// ---------------------------------------------------------------------------
// Minimal in-memory key store (mirrors useMultiFileAuthState behaviour)
// ---------------------------------------------------------------------------

type KeyData = Record<string, Record<string, unknown>>;

function makeInMemoryKeys(initial: KeyData) {
  const data: KeyData = initial;
  return {
    _data: data,
    get<T>(type: string, ids: string[]): { [id: string]: T } {
      const result: { [id: string]: T } = {};
      for (const id of ids) {
        const val = data[type]?.[id];
        if (val !== undefined) result[id] = val as T;
      }
      return result;
    },
    set(newData: KeyData) {
      for (const [type, map] of Object.entries(newData)) {
        data[type] = data[type] ?? {};
        for (const [id, val] of Object.entries(map)) {
          if (val != null) {
            data[type][id] = val;
          } else {
            delete data[type][id];
          }
        }
      }
    },
  };
}
