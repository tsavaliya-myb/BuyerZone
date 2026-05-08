# Buyerzone — Catalog Intelligence System
## WhatsApp Ingestion Module — Implementation Document

**Version:** 1.0 | **Status:** Draft | **Confidential**

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [System Overview](#2-system-overview)
3. [Technology Stack](#3-technology-stack)
4. [Data Models](#4-data-models)
5. [Detailed System Flow](#5-detailed-system-flow)
6. [API Specification](#6-api-specification)
7. [Project Structure](#7-project-structure)
8. [Infrastructure & Deployment](#8-infrastructure--deployment)
9. [Implementation Phases](#9-implementation-phases)
10. [Security Considerations](#10-security-considerations)
11. [Scalability & Module Integration](#11-scalability--module-integration)
12. [Total Cost of Ownership](#12-total-cost-of-ownership)
13. [Open Questions & Decisions Pending](#13-open-questions--decisions-pending)

---

## 1. Executive Summary

Buyerzone's Telegram Ingestion Module already captures product listings from wholesaler Telegram groups. However, a significant portion of wholesalers exclusively or additionally broadcast via **WhatsApp groups and WhatsApp Channels**. This module extends catalog coverage to WhatsApp, ensuring no product listing is missed regardless of which platform a wholesaler uses.

This document defines the architecture, data models, API contracts, infrastructure layout, and implementation roadmap for the **WhatsApp Catalog Ingestion Module**. It is designed as a **parallel ingestion lane** that feeds into the same PostgreSQL + Qdrant shared database, enabling unified search and analytics across all platforms.

> **Module Scope:** This document covers WhatsApp ingestion only. The shared processing pipeline (CLIP, dedup, storage), search APIs, and analytics are defined in their respective module documents. This module reuses those components wherever possible and only introduces what is new.

> **Prerequisite:** The Telegram Ingestion Module and its shared infrastructure (PostgreSQL, Qdrant, Redis, FastAPI, ARQ workers) must already be deployed before this module is added.

---

## 2. System Overview

### 2.1 Problem Statement

Wholesalers broadcast product images and pricing via WhatsApp groups and WhatsApp Channels daily. These messages are separate from Telegram — some wholesalers are WhatsApp-only, and others post to both platforms. Without a WhatsApp ingestion layer, Buyerzone has incomplete catalog coverage: a client asking for a product may be told it is unavailable when it was in fact posted on WhatsApp an hour earlier.

### 2.2 Solution

A dedicated WhatsApp listener microservice built on **Baileys** (Node.js) that authenticates as a WhatsApp user account, monitors admin-approved groups and channels in real time, downloads product images, and enqueues raw message payloads to the **shared Redis ARQ queue**. The existing Python ARQ workers then process these payloads through the same CLIP embedding, dedup, and dual-storage pipeline already used by the Telegram module.

The result: a single unified product catalog searchable across both platforms with zero duplication of the processing infrastructure.

### 2.3 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│              WHATSAPP (Groups + Channels)                            │
│          Wholesaler A    Wholesaler B    Wholesaler N                │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  WhatsApp Web Multi-Device (Baileys)
┌──────────────────────────────▼───────────────────────────────────────┐
│           WA LISTENER SERVICE  (Node.js / Baileys)                   │
│  Pairing-Code Auth → Whitelist Filter → Media Download → Payload     │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  Redis RPUSH  (same queue as Telegram)
┌──────────────────────────────▼───────────────────────────────────────┐
│          SHARED PROCESSING PIPELINE  (Python / ARQ Workers)          │
│   CLIP Embedding → Dedup Check → PostgreSQL + Qdrant Write           │
└──────────┬────────────────────────────────────────┬──────────────────┘
           │                                        │
┌──────────▼──────────┐              ┌──────────────▼──────────────────┐
│    PostgreSQL        │              │          Qdrant                 │
│  (Shared Catalog)    │              │   (Shared Vector Store)         │
└──────────┬──────────┘              └─────────────┬────────────────────┘
           │                                        │
┌──────────▼────────────────────────────────────────▼───────────────────┐
│                   FastAPI + Uvicorn  (Shared REST API)                 │
│       /admin/whatsapp/*   (new)   +   /search/*  /products/*  (shared) │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.4 Key Design Principle: Thin Listener, Shared Pipeline

The WhatsApp listener service does the **minimum work** before handing off:
1. Authenticate and maintain a persistent session
2. Filter incoming messages against the whitelist
3. Download the media file
4. Build a `MessagePayload` (same schema as Telegram payloads)
5. Push to Redis

Everything from CLIP embedding onward is handled by the **existing** Python ARQ workers. No duplication of processing logic.

---

## 3. Technology Stack

### 3.1 New Components (WhatsApp Listener)

| Component | Purpose | Layer |
|---|---|---|
| Node.js 20 LTS | Runtime for Baileys — required by the library | Runtime |
| Baileys (`baileys` v7+) | Open-source WhatsApp Web multi-device client. Most capable WhatsApp automation library. Pinned to the maintained `baileys` package on npm (the older `@whiskeysockets/baileys` fork is deprecated). | Ingestion |
| ioredis | Node.js Redis client — pushes payloads to shared ARQ queue | Queue Bridge |
| sharp | Fast image processing in Node — resize before upload, validate image bytes | Image Util |
| pino | Structured JSON logging (run at `silent` for Baileys internals; INFO for our own logger) | Logging |
| dotenv | Environment variable loading | Config |

> **Library note:** The reference implementation has been validated against `baileys@^7.0.0-rc10`. Use `fetchLatestBaileysVersion()` at startup so the client always negotiates with WhatsApp Web's currently-served protocol version — the version embedded in the npm package can lag and cause `405 Policy Violation` rejections.

### 3.2 Reused Components (No Changes)

| Component | Already Used By |
|---|---|
| Redis (ARQ queue) | Telegram Ingestion, ARQ Workers |
| Python ARQ Workers (`process_message.py`) | Telegram pipeline — reused without modification |
| CLIP singleton (`core/clip.py`) | Already loaded in workers |
| PostgreSQL + SQLAlchemy models | Telegram module |
| Qdrant client (`core/qdrant.py`) | Telegram module |
| Cloudflare R2 storage | Telegram module |
| FastAPI app (`app/main.py`) | Telegram module — new routers added |

### 3.3 Rationale for Key Choices

#### Baileys over WhatsApp Business API
The WhatsApp Business API (Meta Cloud API) requires Facebook Business Manager approval, charges per conversation (₹0.50–₹1.20 per 24h session), and is designed for one-to-many business messaging — not for silently reading groups you are already a member of. Baileys implements the WhatsApp Web multi-device protocol, operates as a regular user account, and has zero per-message cost.

#### Baileys over whatsapp-web.js
`whatsapp-web.js` drives a headless Chromium browser with the WhatsApp Web interface, consuming 800MB–1.5GB RAM. Baileys implements the WebSocket protocol directly with no browser dependency, running in under 150MB RAM — critical for a shared 4GB VPS.

#### Node.js listener bridged to Python workers
Baileys is Node.js only — there is no mature Python equivalent. Rather than rewriting the entire processing pipeline in Node.js, we use Redis as the language bridge. The Node.js service does only I/O work (read message, download media, enqueue). All CPU-intensive work (CLIP inference, database writes) stays in the existing Python workers.

#### ioredis over node-redis
ioredis has a stable, well-documented ARQ-compatible list push interface and handles reconnection internally. It supports the `RPUSH` command needed to push jobs into ARQ's job lists.

---

## 4. Data Models

### 4.1 Schema Changes to Existing Tables

#### monitored_chats — Add platform Column

The existing `monitored_chats` table is extended with a `platform` column to distinguish Telegram and WhatsApp entries. Existing rows default to `telegram`.

```sql
ALTER TABLE monitored_chats
  ADD COLUMN platform VARCHAR(20) NOT NULL DEFAULT 'telegram';

-- Update unique constraint: same chat_id can exist on both platforms
ALTER TABLE monitored_chats DROP CONSTRAINT monitored_chats_chat_id_key;
ALTER TABLE monitored_chats ADD CONSTRAINT monitored_chats_chat_id_platform_unique
  UNIQUE (chat_id, platform);
```

> `chat_id` for WhatsApp is the JID string (e.g. `120363000000000001@g.us`). Store it as TEXT or cast the numeric portion to BIGINT. Use TEXT to avoid JID truncation.

Extend `chat_id` column type if currently BIGINT:
```sql
ALTER TABLE monitored_chats ALTER COLUMN chat_id TYPE TEXT;
```

#### monitored_chats — Full Updated Definition

```sql
-- chat_type values: group | channel | supergroup (Telegram) | wa_group | wa_channel (WhatsApp)
-- platform values: telegram | whatsapp
```

No other structural changes — `platform` + updated `chat_id` type is sufficient.

#### products — source_platform Already Exists

The `products.source_platform` column (`DEFAULT 'telegram'`) already handles multi-platform. WhatsApp products are inserted with `source_platform = 'whatsapp'`. No schema change required.

#### ingestion_logs — No Changes Required

The existing `ingestion_logs` table captures `chat_id`, `telegram_msg_id` (reuse for WhatsApp message ID), `status`, and `product_id`. The column name `telegram_msg_id` is a minor naming inconsistency — rename via migration:

```sql
ALTER TABLE ingestion_logs RENAME COLUMN telegram_msg_id TO message_id;
-- Apply same rename to products table:
ALTER TABLE products RENAME COLUMN telegram_msg_id TO message_id;
```

### 4.2 WA Auth State — Stored in platform_sessions (Same as Telegram)

No separate table. Baileys auth state is stored in the existing `platform_sessions` table with `platform = 'whatsapp'`. This is identical in pattern to how Telegram session strings are stored in `telegram_auth.py`.

| Column | Telegram value | WhatsApp value |
|---|---|---|
| `platform` | `'telegram'` | `'whatsapp'` |
| `phone_number` | linked phone | linked phone |
| `session_data` | Pyrogram session string | Baileys full auth state serialised as JSONB |
| `display_name` | Telegram display name | WhatsApp profile name |
| `status` | `active` / `revoked` | `active` / `revoked` |
| `created_by` | admin user UUID | admin user UUID |

**Auth state lifecycle:**

- On `wa_listener` startup: FastAPI reads the active `platform_sessions` row (`platform='whatsapp'`, `status='active'`), calls `/wa-internal/load-session { authState }`, and Baileys initialises with it — no disk read.
- When Baileys fires `creds.update`: the listener serialises the full auth state and calls `POST /wa-internal/auth-state/save` on itself (stored in-memory); FastAPI periodically flushes this to `platform_sessions` **or** the listener notifies FastAPI via `POST /internal/wa/session-update { authState }` immediately on every `creds.update`.
- On `DELETE /admin/telegram/auth` (revoke): same `platform_sessions` row is marked `status='revoked'` and the listener is reloaded — identical to the Telegram revoke flow.
- No disk volume needed for auth state. `wa_sessions/` directory is **removed** from the docker-compose volume mounts.



### 4.3 MessagePayload — Shared Queue Contract

The Node.js listener and the Python workers communicate via this JSON payload pushed to Redis. It is **identical in shape** to the Telegram payload so workers need zero branching:

```json
{
  "source_platform": "whatsapp",
  "chat_id": "120363000000000001@g.us",
  "chat_name": "Buyerzone Wholesalers WA",
  "chat_type": "wa_group",
  "message_id": "3EB0A1B2C3D4E5F6A7B8",
  "sender_id": "919876543210@s.whatsapp.net",
  "caption": "Shirt ₹350 available in all sizes",
  "image_data_b64": "<base64-encoded-jpeg>",
  "received_at": "2026-05-03T10:30:00Z"
}
```

> `image_data_b64`: The Node.js service downloads the image and encodes it as base64 before pushing. This avoids file-system coupling between the Node container and Python worker containers. Max image size after resize: ~300KB.

---

## 5. Detailed System Flow

### 5.1 Authentication Flow (Admin UI Driven)

Baileys auth state is stored in `platform_sessions` (DB) — no disk files, no env-var phone numbers. The entire flow is initiated from the Admin UI by an authenticated admin, identical in structure to Telegram's UI-driven OTP flow in `telegram_auth.py`.

```
STARTUP (every container boot)
────────────────────────────────────────────────────────────
FastAPI lifespan:
  → SELECT platform_sessions WHERE platform='whatsapp' AND status='active'
  → If found:
      POST /wa-internal/load-session { authState: <JSONB from session_data> }
      → Baileys initialises with stored creds, connects immediately
      → Listener state: 'connected'
  → If not found:
      POST /wa-internal/load-session { authState: null }
      → Baileys starts with empty state, waits for pairing
      → Listener state: 'awaiting_pair_code'

FIRST-TIME PAIRING (Admin UI)
────────────────────────────────────────────────────────────
Admin: opens Admin → WhatsApp → status shows "Not paired"
       enters phone number (digits only, e.g. 919876543210) → clicks Pair

  POST /api/v1/admin/whatsapp/auth/send-code { phone }   ← JWT Admin
    → normalise + validate phone (7–15 digits, no '+')
    → POST /wa-internal/pair { phone }
        → fetchLatestBaileysVersion() + makeWASocket(...)
        → Wait ~3s for socket handshake
        → sock.requestPairingCode(phone)
        → Listener state: 'pair_pending'
        → Returns { login_id, code: "ABCD-EFGH", expires_in: 60 }
    → Returns { login_id, code, expires_in } to Admin UI

Admin: UI shows "ABCD-EFGH" with 60s countdown
       Operator opens WhatsApp on linked phone:
         Settings → Linked Devices → Link a device
                  → "Link with phone number instead"
                  → Enters code

  Baileys fires creds.update:
    → Listener serialises full auth state as JSONB
    → POST /internal/wa/session-update { authState, phone, display_name }
        (Node → FastAPI — only outbound call Node ever makes)
        → UPSERT platform_sessions (platform='whatsapp', status='active',
                                    session_data=<authState JSONB>,
                                    phone_number=phone, display_name=display_name)
    → Subsequent creds.update events (key rotation) repeat this upsert

  Baileys fires connection.update { connection: 'open' }:
    → Listener state: 'connected'
    → Whitelist loaded from monitored_chats
    → Ingestion begins

SUBSEQUENT RESTARTS
────────────────────────────────────────────────────────────
  → Lifespan loads auth state from DB → Baileys connects, no operator action

RE-PAIRING (after 401 loggedOut or 405 Policy Violation)
────────────────────────────────────────────────────────────
  → Listener auto-transitions to 'requires_repair', stops ingesting
  → Admin UI shows "Re-pair required" banner

  DELETE /api/v1/admin/whatsapp/auth   ← JWT Admin
    → UPDATE platform_sessions SET status='revoked'
    → POST /wa-internal/reset  (clears in-memory creds, reinitialises empty socket)
    → Listener state: 'awaiting_pair_code'
  → Admin repeats pairing flow above
```

> **Pairing code is the only supported auth path.** `printQRInTerminal` stays `false`, the `qr` field from `connection.update` is ignored, and there is no `/qr` endpoint anywhere in the system.

### 5.2 Admin — Adding Monitored Chats

The flow mirrors the Telegram admin UX (search-then-add) but accepts **either a name fragment or an invite code** in a single resolve endpoint. The bot **never auto-joins**: the operator joins the chat from the linked WhatsApp account first, and the bot's job is only to resolve-and-validate-and-add.

This design protects the account from WhatsApp's automation heuristics (rapid programmatic joins are a common ban trigger) and keeps a clean separation: human owns membership, bot owns monitoring.

#### 5.2.1 Supported chat types

| Type | JID suffix | Invite link shape | Resolve API |
|---|---|---|---|
| WA Group | `@g.us` | `https://chat.whatsapp.com/<code>` | `sock.groupGetInviteInfo(code)` |
| WA Community (parent / child sub-group) | `@g.us` | `https://chat.whatsapp.com/<code>` | `sock.groupGetInviteInfo(code)` — same call as groups; community-ness is exposed in metadata flags. Each sub-group is added separately. |
| WA Channel (Newsletter) | `@newsletter` | `https://whatsapp.com/channel/<code>` | `sock.newsletterMetadata("invite", code)` |

> Communities are not a single monitored entity. The parent announcement group and each sub-group are distinct JIDs. The admin adds whichever ones carry product listings.

#### 5.2.2 Unified resolve endpoint

```
Admin Request: POST /admin/whatsapp/chats/resolve
Body: { "query": "<name fragment OR full invite URL>" }
```

The listener decides between two paths based on input shape:

**Path A — Name search (input does not start with `http`)**

```
→ FastAPI calls WA Listener: GET /wa-internal/joined?q=<query>
→ Baileys fetches joined chats:
    groups    = await sock.groupFetchAllParticipating()        // map jid → metadata
    channels  = sock.newsletterListSubscribed?.() ?? []        // followed newsletters
                (fallback: cache populated from CHANNEL_LINKS resolved at startup)
→ Case-insensitive substring match on group `subject` and channel name
→ Return: [
    {
      "jid": "120363...@g.us",
      "name": "Buyerzone Wholesalers WA",
      "type": "wa_group",          // or wa_channel
      "is_community_parent": false,
      "is_community_subgroup": false,
      "participant_count": 142,
      "already_monitored": false   // looked up against monitored_chats
    },
    ...
  ]
```

If the operator hasn't joined the chat yet, it won't appear here. The UI should surface a hint: "Don't see it? Paste the invite link instead."

**Path B — Invite link (input starts with `http`)**

```
→ Parse link → { kind: 'group' | 'channel', code: <last path segment> }

→ For groups (chat.whatsapp.com):
    info = await sock.groupGetInviteInfo(code)
    jid  = info.id                              // 120363...@g.us
    name = info.subject

→ For channels (whatsapp.com/channel):
    meta = await sock.newsletterMetadata("invite", code)
    jid  = meta.id
    name = meta.thread_metadata?.name?.text
        || meta.threadMetadata?.name?.text
        || meta.name || meta.subject

→ Membership check (CRITICAL):
    For groups:    is jid present in groupFetchAllParticipating()?
    For channels:  is jid present in subscribed-newsletter list / channel cache?

  NOT a member  → 409 Conflict
                  { "error": "not_joined",
                    "message": "Resolved '<name>' but the bot account is not yet a
                                member. Open WhatsApp on the linked phone, join via
                                this invite link, then retry." ,
                    "preview": { "jid": ..., "name": ..., "type": ... } }
                  (Preview is returned so the admin UI can show what they're about to
                  monitor — but the row is NOT inserted.)

  IS a member   → 200 OK, same shape as Path A's list element
                  with already_monitored set from monitored_chats lookup.
```

#### 5.2.3 Add endpoint

```
Admin Request: POST /admin/whatsapp/chats/add
Body: { "jid": "<resolved jid>", "chat_name": "<optional override>" }

  → Re-validate JID is currently in joined chats (defensive — operator may have
    left between resolve and add)
  → INSERT into monitored_chats (
        platform='whatsapp',
        chat_id=<jid>,
        chat_type='wa_group' | 'wa_channel' | 'wa_community',
        chat_name=<resolved or overridden name>
    )
  → Notify WA Listener: POST /wa-internal/whitelist/reload
  → In-memory JID Set in Node.js updated immediately
  → If chat_type='wa_channel': fire-and-forget
        sock.newsletterSubscribeLiveUpdates(jid)
    so message events start flowing for this newsletter
  → Listener begins capturing messages from this JID instantly
```

#### 5.2.4 Operator runbook (UI copy)

```
To add a WhatsApp group / community sub-group / channel:

  1. On the phone linked to the bot, open WhatsApp and JOIN the chat
     (via invite link, QR, or accept-invite flow).
     - Groups & community sub-groups: chat.whatsapp.com/<code>
     - Channels:                      whatsapp.com/channel/<code>

  2. In Buyerzone Admin → WhatsApp → Add Chat:
       - Type a name fragment (matches anything you have already joined),
         OR paste the full invite link.
       - Pick the result, click Add.

  3. The bot starts capturing on the next image posted to that chat.
     No restart needed.

If you paste an invite link and see "not_joined": you haven't joined the
chat on the linked phone yet. Do step 1, then retry.
```

### 5.3 Ingestion Flow (Real-Time, 24/7)

if message have multiple images then we only need first image only.

```
Event: New batch arrives via sock.ev.on('messages.upsert', { messages, type })
                │
                ▼
FILTER 1: type ∈ {'notify', 'append'}?
          (skip 'history' sync batches, 'prepend', etc.)
          NO  → discard silently
          YES → continue per-message

For each msg in messages:
                │
                ▼
FILTER 2: msg.key.fromMe === true?
          YES → skip (own messages, e.g. echoes)
                │
                ▼
FILTER 3: msg.key.remoteJid in monitored JID whitelist?
          NO  → discard silently
          YES → continue
                │
                ▼
UNWRAP:   msg.message envelope can be wrapped — peel layers in order:
            ephemeralMessage.message
            viewOnceMessage.message
            viewOnceMessageV2.message
            viewOnceMessageV2Extension.message
            documentWithCaptionMessage.message
            editedMessage.message
          (fall back to msg.message itself)
                │
                ▼
FILTER 4: Does the unwrapped content carry an imageMessage?
          Look at:
            content.imageMessage
            content.extendedTextMessage?.contextInfo?.quotedMessage?.imageMessage
          YES → continue
                │
                ▼
FILTER 5: Does caption match "out of stock" | "stock out" |
          "not available" | "sold out" (case-insensitive)?
          YES → log as skipped (out of stock) → discard
          NO  → continue
                │
                ▼
DOWNLOAD: Two-path strategy (validated in reference implementation):

          if (imageMsg.mediaKey && imageMsg.mediaKey.length > 0):
              // Encrypted media path — normal case
              buffer = await downloadMediaMessage(msg, 'buffer', {})
          else:
              // Channel/newsletter or relayed message with no mediaKey
              directUrl = imageMsg.url
                       || (imageMsg.directPath
                             ? `https://mmg.whatsapp.net${imageMsg.directPath}`
                             : null)
              if (!directUrl) → log + skip
              buffer = Buffer.from(await (await fetch(directUrl)).arrayBuffer())

          → Validate magic bytes: JPEG (FF D8 FF) or PNG (89 50 4E 47)
          → Resize to max 1024px longest edge using sharp (preserve aspect)
          → Encode to base64
                │
                ▼
BUILD:    Construct MessagePayload JSON object
          → source_platform: 'whatsapp'
          → chat_id:    msg.key.remoteJid
          → chat_type:  isJidGroup(jid) ? 'wa_group'
                       : jid.endsWith('@newsletter') || jid.endsWith('@broadcast')
                         ? 'wa_channel' : 'personal'
          → message_id: msg.key.id
          → sender_id:  derived from msg.key.participant (groups/channels) or
                        msg.key.remoteJid when remoteJid ends with
                        '@s.whatsapp.net' or '@c.us' (1:1 chats).
                        Strip device suffix (':NN') and validate /^\d{7,15}$/.
          → sender_name: msg.pushName || sender_id
          → caption:    imageMsg.caption || ''
          → image_data_b64: base64 string
          → received_at: ISO timestamp from msg.messageTimestamp (unix seconds → ms)
                │
                ▼
ENQUEUE:  ioredis.rpush('arq:queue:process_message', JSON.stringify(payload))
          → Node.js listener returns immediately (non-blocking)
          → Python ARQ worker picks up and processes
```

### 5.4 Processing Pipeline (Existing Python Workers — No Changes)

The ARQ worker's `process_message` task already handles both platforms via `source_platform` field. 

- **Telegram path:** image arrives pre-downloaded as base64 in payload → decoded in Python
- **WhatsApp path:** image arrives pre-downloaded as base64 in payload → decoded in Python

Everything downstream (validation, R2 upload, CLIP, dedup, PostgreSQL+Qdrant write) is **identical**.

```
ARQ Worker picks up MessagePayload (whatsapp or telegram — same code path)
                │
                ▼
DECODE:   base64 decode → raw image bytes
          → Validate magic bytes
          → Resize to 224×224 for CLIP (preserve original separately)
                │
                ▼
UPLOAD:   Upload original to Cloudflare R2
          Key: products/{platform}/{chat_id}/{msg_id}/{uuid}.jpg
                │
                ▼
PARSE:    Extract price from caption (same regex — INR)
          Extract product name
                │
                ▼
EMBED:    CLIP ViT-B/32 → 512-dim normalised vector
                │
                ▼
DEDUP:    Qdrant cosine similarity > 0.96, same wholesaler, last 30 days
          DUPLICATE → log → skip
          UNIQUE    → continue
                │
                ▼
PERSIST:  BEGIN transaction
          1. INSERT products (source_platform='whatsapp')
          2. Upsert Qdrant point
          3. INSERT ingestion_logs
          COMMIT
```

### 5.5 WhatsApp Channels (Newsletters)

WhatsApp Channels (called "Newsletters" in Baileys) behave differently from groups:

| Property | Groups | Channels (Newsletters) |
|---|---|---|
| JID suffix | `@g.us` | `@newsletter` |
| Sender identity | Participant JID available | Admin only — anonymous (no usable phone number) |
| Resolve from invite link | n/a | `sock.newsletterMetadata("invite", <code>)` where `<code>` is the last path segment of `https://whatsapp.com/channel/<code>` |
| Resolve from JID | n/a | `sock.newsletterMetadata("jid", <jid>)` |
| Live updates | Always-on | Must call `sock.newsletterSubscribeLiveUpdates(jid)` after first message — without it, message events for that channel may not flow |
| Message event | `messages.upsert` | `messages.upsert` (same event) |
| Join mechanism | Invite link | Subscribe button |

**Channel name resolution — resolved once at add-time, stored in DB:**

No in-memory caching of JID → name mappings. Names are resolved during the admin `chats/resolve` + `chats/add` flow and persisted to `monitored_chats.chat_name`. The listener never needs to look up a name at runtime.

- `POST /admin/whatsapp/chats/resolve` calls `/wa-internal/resolve-link` → Baileys resolves the invite link and returns `{ jid, name, type }`. Name is shown in the admin UI for confirmation.
- `POST /admin/whatsapp/chats/add` inserts the row with `chat_name = <resolved name>`. This is the permanent record.
- During ingestion, `chat_name` in the `MessagePayload` is sourced from the in-memory whitelist Set which is loaded from `monitored_chats` on startup and on every `/wa-internal/whitelist/reload` call. No Baileys API call at message-receive time.

After a channel is added, fire-and-forget `sock.newsletterSubscribeLiveUpdates(jid)` so message events start flowing. This is the only channel-specific runtime call.

The listener handles both group and channel JIDs transparently — the same `messages.upsert` handler fires for both. The `chat_type` in `monitored_chats` is set to `wa_group` or `wa_channel` for admin visibility, but the ingestion logic is identical.

> **Sender attribution for channels:** because channel posts are anonymous from the admin, `sender_id` falls back to the channel JID itself and `sender_name` to the channel name. Wholesaler attribution must be done by mapping `chat_id → wholesaler_id` rather than `sender_id → wholesaler_id`.

### 5.6 Disconnect & Reconnect Handling

The reference implementation distinguishes three close-codes from `connection.update`'s `lastDisconnect.error.output.statusCode`:

| Status code | Meaning | Action |
|---|---|---|
| `DisconnectReason.loggedOut` (401) | Device was unlinked from the phone | Do NOT auto-reconnect. Surface admin alert.  + re-pairs. |
| `405` | **Policy Violation** — WhatsApp rejected the connection (often stale auth state after protocol changes, or a banned/flagged account) | Do NOT auto-reconnect. Process exits 1. Do not retry in a loop — you will get rate-limited. |
| Anything else | Transient (network, server restart) | Reconnect by re-invoking `startBot()`. Baileys' internal WebSocket layer handles short blips; this outer reconnect handles full socket teardowns. |

`creds.update` must be wired to `saveCreds` from `useMultiFileAuthState` so credential rotations (rolling keys, app-state sync) are persisted.

---

## 6. API Specification

All new endpoints are under `/api/v1/admin/whatsapp/`. They follow the same JWT Bearer auth pattern as the Telegram admin endpoints.

### 6.1 New WhatsApp Admin  (in FastAPI)

| Endpoint | Description | Auth |
|---|---|---|
| `GET /admin/whatsapp/status` | Baileys connection status: `connected`, `pair_pending`, `disconnected`, `awaiting_pair_code`. | JWT Admin |
| `POST /admin/whatsapp/pair` | Request pairing code. Body: `{ "phone": "919876543210" }` (digits only). Returns `{ "code": "ABCD-EFGH", "expires_in": 60 }`. | JWT Admin |
| `POST /admin/whatsapp/chats/resolve` | Unified resolve. Body: `{ "query": "<name fragment OR invite URL>" }`. Returns matching joined chats, or for an invite link returns the resolved chat plus a `not_joined` error if the bot is not yet a member. See §5.2.2. | JWT Admin | 
| `POST /admin/whatsapp/chats/add` | Add a resolved JID to the monitored whitelist. Body: `{ "jid": "...", "chat_name": "..." }`. Re-validates membership, inserts into `monitored_chats`, triggers whitelist reload, subscribes to newsletter live updates if channel. | JWT Admin |
| `DELETE /admin/whatsapp/chats/{id}` | Remove WA chat from whitelist. Does NOT leave/unsubscribe on WhatsApp — that is the operator's action. | JWT Admin |
| `GET /admin/whatsapp/chats` | List all monitored WA chats with status and message counts. | JWT Admin |

### 6.2 Shared Endpoints — No Changes Required

The following existing endpoints work for WhatsApp products automatically because `source_platform` is stored per product:

| Endpoint | WhatsApp Support |
|---|---|
| `GET /products` | Add `?platform=whatsapp` filter |
| `GET /products/{id}` | Works — returns `source_platform: "whatsapp"` |
| `POST /search/image` | Works — searches across all platforms |
| `GET /search/text` | Works — full-text search covers all products |
| `GET /admin/logs` | Add `?platform=whatsapp` filter |
| `GET /admin/stats` | Returns per-platform breakdown |

### 6.3 Internal WA Listener HTTP API

The WA Listener (Node.js) exposes a small internal HTTP API consumed only by FastAPI. Not exposed externally.

| Endpoint | Description |
|---|---|
| `GET /wa-internal/status` | Connection state + session info |
| `GET /wa-internal/joined?q=<frag>` | List joined groups + subscribed channels, optionally filtered by name fragment (case-insensitive substring on `subject` / channel name). Used by Path A of resolve. |
| `POST /wa-internal/resolve-link` | Body: `{ "url": "<invite url>" }`. Detects link kind, calls `groupGetInviteInfo` or `newsletterMetadata("invite", code)`, returns `{ jid, name, type, is_member }`. Used by Path B of resolve. |
| `POST /wa-internal/whitelist/reload` | Trigger in-memory whitelist refresh from DB. |
| `POST /wa-internal/subscribe-newsletter` | Body: `{ "jid": "...@newsletter" }`. Calls `sock.newsletterSubscribeLiveUpdates(jid)`. Invoked after a channel is added to monitored chats. |
| `POST /wa-internal/pair` | Initiate pairing code flow. |

Internal API is bound to `127.0.0.1` within Docker network only.

---

## 7. Project Structure

### 7.1 New: WhatsApp Listener Service (Node.js)

```
wa-listener/                         # New top-level service directory
├── src/
│   ├── index.ts                     # Entry point — starts Baileys + HTTP server
│   ├── config.ts                    # Env var loading (dotenv)
│   ├── auth.ts                      # Auth state management (Postgres)
│   ├── listener.ts                  # Baileys client setup + message handler
│   ├── downloader.ts                # downloadMediaMessage wrapper + validation
│   ├── payload.ts                   # MessagePayload builder
│   ├── queue.ts                     # ioredis RPUSH to ARQ queue
│   ├── http.ts                      # Internal HTTP API (Express, minimal)
│   └── logger.ts                    # pino structured logger
├── package.json
├── tsconfig.json
└── Dockerfile                       # Node 20 Alpine
```

### 7.2 Changes to Existing Python Services

```
app/
├── api/v1/
│   ├── admin.py                     # EXISTING — Telegram admin routes
│   └── whatsapp_admin.py            # NEW — /admin/whatsapp/* routes
│
├── services/
│   ├── wa_chat_resolver.py          # NEW — calls WA Listener internal API
│   └── processing.py                # MODIFIED — handle whatsapp messages
│
├── workers/tasks/
│   └── process_message.py           # MODIFIED — handle whatsapp messages
│
└── schemas/
    └── whatsapp_admin.py            # NEW — Pydantic schemas for WA admin APIs
```

### 7.3 Full Updated Directory Tree

```
bz-core/
├── app/                             # Python FastAPI (mostly unchanged)
│   ├── api/v1/
│   │   ├── admin.py
│   │   ├── whatsapp_admin.py        # NEW
│   │   ├── search.py
│   │   ├── products.py
│   │   └── internal.py
│   ├── services/
│   │   ├── ingestion.py             # Telegram listener (unchanged)
│   │   ├── processing.py            # MODIFIED
│   │   ├── wa_chat_resolver.py      # NEW
│   │   ├── search.py
│   │   ├── storage.py
│   │   ├── chat_resolver.py
│   │   └── staleness.py
│   ├── workers/tasks/
│   │   ├── process_message.py       # MODIFIED
│   │   └── staleness_check.py
│   └── schemas/
│       ├── whatsapp_admin.py        # NEW
│       └── ...
│
├── wa-listener/                     # NEW — Node.js Baileys service
│   ├── src/
│   │   ├── index.ts
│   │   ├── auth.ts
│   │   ├── listener.ts
│   │   ├── whitelist.ts
│   │   ├── downloader.ts
│   │   ├── payload.ts
│   │   ├── queue.ts
│   │   └── http.ts
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
│
├── alembic/versions/
│   └── xxxx_add_platform_to_monitored_chats.py   # NEW migration
│
├── wa_sessions/                     # Baileys auth state (gitignored)
├── docker-compose.yml               # MODIFIED — add wa_listener service
├── .env.example                     # MODIFIED — add WA env vars
└── pyproject.toml
```

---

## 8. Infrastructure & Deployment

### 8.1 New Docker Compose Service

Add to existing `docker-compose.yml`:

```yaml
services:

  # --- Existing services unchanged ---
  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    env_file: .env
    depends_on: [postgres, redis, qdrant]
    volumes:
      - ./sessions:/app/sessions

  worker:
    build: .
    command: python -m arq app.workers.arq_worker.WorkerSettings
    env_file: .env
    depends_on: [postgres, redis, qdrant]
    volumes:
      - ./sessions:/app/sessions

  ingestion:
    build: .
    command: python -m app.services.ingestion
    env_file: .env
    restart: always
    volumes:
      - ./sessions:/app/sessions

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: buyerzone
      POSTGRES_USER: buyerzone
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:latest
    volumes:
      - qdrant_data:/qdrant/storage

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  # --- NEW: WhatsApp Listener ---
  wa_listener:
    build: ./wa-listener
    restart: always
    env_file: .env
    environment:
      WA_INTERNAL_PORT: 3001
    ports: []                         # Not exposed externally
    expose:
      - "3001"                        # Internal only — accessible to api service
    depends_on: [redis, postgres]
    # No volume mount for auth state — Baileys creds stored in platform_sessions (DB)

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

### 8.2 New Environment Variables

Add to `.env` (and `.env.example`):

```env
# WhatsApp Listener
WA_LISTENER_URL=http://wa_listener:3001     # Internal Docker network URL
WA_INTERNAL_SECRET=your_internal_secret    # Shared secret for FastAPI → WA listener calls
WA_LOG_LEVEL=info
```

### 8.3 wa-listener Dockerfile

```dockerfile
FROM node:20-alpine

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci --only=production

# Build TypeScript
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

# Session directory
RUN mkdir -p /app/wa_sessions

CMD ["node", "dist/index.js"]
```

### 8.4 wa-listener package.json (Key Dependencies)

```json
{
  "dependencies": {
    "baileys": "^7.0.0-rc10",
    "ioredis": "^5.4.1",
    "sharp": "^0.33.4",
    "express": "^4.19.2",
    "pino": "^9.2.0",
    "dotenv": "^16.4.5"
  },
  "devDependencies": {
    "typescript": "^5.4.5",
    "@types/express": "^4.17.21",
    "@types/node": "^20.14.0"
  },
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "dev": "ts-node src/index.ts"
  }
}
```

### 8.5 Authentication (Admin UI Runbook) (UI not need to be developed now)

WhatsApp pairing is driven **entirely from the Admin UI**. There are no shell commands, no `docker compose` steps, and no log-watching involved in the operator-facing flow. The container is assumed to be running; whether the listener is paired is a state shown in the UI.

**Listener states surfaced in the UI** (from `GET /admin/whatsapp/status`):

| State | What the UI shows | Operator action |
|---|---|---|
| `awaiting_pair_code` | "Not paired. Enter the WhatsApp business number to start." | Type the phone number (digits only) and click **Pair**. |
| `pair_pending` | "Pairing code: `ABCD-EFGH` — expires in 53s." | Enter the code in WhatsApp on the linked phone. |
| `connected` | "Paired ✓ — connected as +91…" with last-seen timestamp. | None. |
| `disconnected` | "Disconnected, retrying…" with reason and retry counter. | None unless reason is permanent (see below). |
| `requires_repair` | "Session ended — re-pair required. Reason: `loggedOut` / `policy_violation`." with **Re-pair** button. | Click **Re-pair** → returns the listener to `awaiting_pair_code`, then enter the number again. |

**First-time pairing flow (UI):**

1. Open Admin → WhatsApp. Status shows `awaiting_pair_code`.
2. Enter the WhatsApp business number (digits only, country code + national number, e.g. `919876543210`). Click **Pair**.
3. UI displays the 8-character code with a 60-second countdown.
4. On the linked phone: WhatsApp → Settings → Linked Devices → Link a device → "Link with phone number instead" → enter the code.
5. UI transitions to `connected` within a few seconds; configured channels begin resolving and ingestion starts automatically.

**Re-pairing flow (UI):**

When a 401 (`loggedOut`) or 405 (Policy Violation) occurs the listener moves itself to `requires_repair`, clears its in-memory connection, and stops ingesting. The operator clicks **Re-pair** in the UI; FastAPI calls the listener's internal API to wipe `wa_sessions/auth_pairing/`, transitions back to `awaiting_pair_code`, and the operator repeats steps 2–5 above.

> No SSH, no `docker compose`, no `rm -rf` is ever required from operators. Those remain available as a break-glass path for engineers, but they are not part of the documented procedure.

---

## 9. Implementation Phases

### Phase 1 — Baileys Service Foundation (Week 1)

**Goal:** WA Listener container connects to WhatsApp and maintains a stable session.

1. Set up `wa-listener/` Node.js project with TypeScript
2. Implement Baileys auth on `useMultiFileAuthState` — pairing code only, `printQRInTerminal: false`
3. Implement `/wa-internal/pair` (request pairing code) and `/wa-internal/status` (auth state machine: `awaiting_pair_code` → `pair_pending` → `connected` → `disconnected` / `requires_repair`)
4. Implement reconnection logic for transient closes; surface 401/405 as `requires_repair` (no auto-reconnect)
5. Internal HTTP API skeleton (`/wa-internal/status`, `/wa-internal/pair`, `/wa-internal/repair`)
6. Add `wa_listener` service to docker-compose
7. Verify: pair via API → session persists across container restarts → trigger repair → re-pair end-to-end

### Phase 2 — Schema Migration & Whitelist (Week 1–2)

**Goal:** Database supports multi-platform chats; admin can add WA groups.

1. Alembic migration: add `platform` column to `monitored_chats`
2. Alembic migration: rename `telegram_msg_id` → `message_id` (if decided)
4. Implement `/wa-internal/groups` — fetches joined groups + channels via Baileys
5. Implement `/admin/whatsapp/chats/*` FastAPI routes + `wa_chat_resolver.py`
6. Verify: admin can search WA groups, add to whitelist, whitelist reloads in Node.js

### Phase 3 — Message Listener + Queue Bridge (Week 2)

**Goal:** Product image messages from whitelisted WA groups are enqueued to Redis.

1. Implement `listener.ts` — Baileys `messages.upsert` handler
2. Implement all filter stages (type, whitelist, has image, out-of-stock text)
3. Implement `downloader.ts` — `downloadMediaMessage` with validation + resize
4. Implement `payload.ts` — build `MessagePayload` JSON
5. Implement `queue.ts` — `ioredis.rpush` into ARQ queue
6. Verify: send test image to monitored WA group → payload appears in Redis

### Phase 4 — Python Worker Integration (Week 2–3)

**Goal:** WhatsApp payloads flow through the existing processing pipeline end-to-end.

1. Modify `process_message.py` — add `image_data_b64` branch (base64 decode)
2. Verify R2 upload succeeds for WhatsApp images
3. Verify CLIP embedding generated correctly
4. Verify PostgreSQL insert with `source_platform='whatsapp'`
5. Verify Qdrant point inserted with correct payload
6. Verify dedup logic works cross-platform (same product, different platforms)
7. End-to-end test: WA group message → product searchable via `/search/image`

### Phase 5 — Admin Dashboard & Hardening (Week 3)

**Goal:** Operations team can manage WA chats, monitor ingestion health.

1. `/admin/whatsapp/status` — surface listener state machine (`awaiting_pair_code` / `pair_pending` / `connected` / `disconnected` / `requires_repair`) to admin UI
2. `/admin/stats` — add WhatsApp breakdown to existing stats endpoint
3. `/admin/logs` — add `?platform=whatsapp` filter
4. Session revocation detection — flip listener to `requires_repair` on 401/405 and surface a re-pair prompt in the UI
5. Dead-letter queue handling for WA failed jobs (same as Telegram)
6. Load test: 100 WA messages/hour sustained → verify no queue backlog
7. Documentation: admin UI runbook for pairing and re-pairing

---

## 10. Security Considerations

### 10.1 Authentication Layers

| Layer | Mechanism |
|---|---|
| Admin WhatsApp API | JWT Bearer token — same as existing admin endpoints |
| FastAPI → WA Listener | Shared secret header (`X-Internal-Secret`) on all `/wa-internal/*` calls |
| Baileys Session | Auth state stored with `700` permissions. Never committed to git. |
| WhatsApp Account | Dedicated business number — not personal. Registered as linked device. |

### 10.2 Baileys Session Security

- Auth state backed up to R2 on schedule (same as PostgreSQL backups)
- If session file is compromised, revoke immediately via WhatsApp mobile: Settings → Linked Devices → Remove device
- Session file contains cryptographic keys — treat with same sensitivity as private keys

### 10.3 WhatsApp Account Risk

WhatsApp aggressively bans accounts that exhibit automation behaviour. Mitigations:

| Risk | Mitigation |
|---|---|
| Account ban for automation | Use a dedicated business number, not a personal one |
| Ban for high message volume | We are a **reader** only — we never send messages |
| Session invalidation | Reconnection logic + admin alert on disconnect |
| Rate limiting by WhatsApp | Baileys handles WebSocket reconnection internally |
| Number reported as spam | Only join groups/channels through legitimate invite links |

### 10.4 Media Privacy

- WhatsApp images in monitored groups are business product listings shared voluntarily by wholesalers
- Images are stored in the same Cloudflare R2 bucket as Telegram images under `products/whatsapp/...`
- No end-to-end encrypted personal messages are read — only whitelisted business group content

### 10.5 Internal API Isolation

- WA Listener HTTP API binds to container-internal network only
- Not exposed via Nginx or any external port mapping
- Docker network isolates it from the internet
- FastAPI calls it using Docker service DNS (`http://wa_listener:3001`)

---

## 11. Scalability & Module Integration

### 11.1 Capacity Estimate (WhatsApp Contribution)

| Metric | Estimate |
|---|---|
| WA messages per day | 200–500 (subset of wholesalers on WA) |
| Additional products/year | ~50,000 |
| Combined catalog after 1 year | ~150,000 (Telegram + WhatsApp) |
| Qdrant memory increase | ~100MB additional (50k × 512-dim) |
| R2 storage increase | ~25GB additional |
| Worker CPU impact | Negligible — same CLIP pipeline |

### 11.2 Cross-Platform Dedup

A wholesaler may post the same product on both Telegram and WhatsApp. The existing Qdrant dedup (cosine similarity > 0.96 within 30 days, same `wholesaler_id`) already handles this — regardless of which platform the message arrived on. No additional logic required, provided the same `wholesaler_id` is assigned to a wholesaler across both platforms.

> **Admin action:** When registering a wholesaler, link both their Telegram ID and their WhatsApp JID to the same `wholesaler` row. This enables cross-platform dedup.

Schema addition to `wholesalers` table:
```sql
ALTER TABLE wholesalers ADD COLUMN wa_jid VARCHAR(100) UNIQUE;
```

### 11.3 Module Integration Points

Downstream modules consume the unified product catalog without needing to know the source platform:

- **Analytics Module** — can now show Telegram vs WhatsApp contribution charts
- **Search API** — returns products from both platforms in unified results
- **Order Management** — wholesaler contact info includes both Telegram and WhatsApp contact
- **Staleness Module** — staleness logic applies equally to all products regardless of platform

### 11.4 Scaling Path

- **Multiple WA accounts:** Run multiple `wa_listener` containers with different session directories and phone numbers. Each pushes to the same Redis queue. Useful if one account covers a different set of groups.
- **Worker scaling:** ARQ workers are stateless — add more `worker` containers to handle increased queue volume. No changes to WA listener.
- **Baileys WebSocket:** Single connection handles all groups the account is joined to — no per-group resource cost.

---

## 12. Total Cost of Ownership

| Component | Additional Cost |
|---|---|
| wa_listener container | ~50MB RAM on existing VPS — **zero additional server cost** |
| Baileys library | Free — open source (MIT) |
| WhatsApp account | ₹0/month — standard WhatsApp account on a SIM |
| Node.js 20 Alpine image | ~60MB disk — negligible |
| Additional R2 storage (~25GB/year) | ~$0.38/month |
| Additional PostgreSQL storage | Negligible |
| **Total additional monthly cost** | **~$0.38/month** |

> The WhatsApp module adds near-zero marginal cost to the existing infrastructure. The entire combined system (Telegram + WhatsApp ingestion, CLIP, dual-store) runs on the same single Hetzner VPS.

---

## 13. Open Questions & Decisions Pending

| Question | Details | Recommendation | Owner's Response |
|---|---|---|---|
| Rename `telegram_msg_id` column | Rename to `message_id` in `products` and `ingestion_logs` for platform neutrality? | Yes — clean up now before WA data enters the tables. One migration. | Yes |
| Wholesaler WA JID mapping | Add `wa_jid` column to `wholesalers` table for cross-platform dedup and contact info? | Yes — required for accurate dedup and order management integration. | yes |
| View-once message handling | WhatsApp "view once" images — Baileys can still download them. Should they be ingested? | Yes — wholesalers sometimes use view-once for freshness signalling. Ingest and store. | yes |
| Stale product threshold for WA | Same 30-day default as Telegram, or different? | Same default — keep configuration unified. Configurable per wholesaler. |  same - 30 day|
| Cross-platform dedup scope | Dedup across platforms (same image from WA + Telegram = 1 product) or per-platform only? | Cross-platform — same `wholesaler_id` + cosine > 0.96 already handles it. Verify. | per-platform |

---

*Buyerzone Catalog Intelligence System — WhatsApp Ingestion Module — v1.0 — Confidential*
