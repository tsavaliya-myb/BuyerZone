# Buyerzone — Catalog Intelligence System
## Telegram Ingestion Module — Implementation Document

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
11. [Scalability & Future Modules](#11-scalability--future-modules)
12. [Total Cost of Ownership](#12-total-cost-of-ownership)
13. [Open Questions & Decisions Pending](#13-open-questions--decisions-pending)

---

## 1. Executive Summary

Buyerzone operates as a B2B dropshipping intermediary sourcing products from 50–60 wholesalers and fulfilling orders for downstream reseller clients. Currently, wholesalers broadcast product listings — images with pricing captions — via Telegram groups and channels. This information is unstructured, ephemeral, and unsearchable, causing critical inventory visibility failures when clients enquire about product availability.

This document defines the architecture, data models, API contracts, infrastructure layout, and implementation roadmap for the **Telegram Catalog Intelligence System** — the foundational ingestion module of the Buyerzone platform. Downstream modules (analytics dashboard, order management, client-facing catalog) will consume data produced by this module.

> **Module Scope:** This document covers the Telegram Ingestion Module only. WhatsApp ingestion, client-facing search UI, order management, and analytics are separate modules addressed in their respective documents.

---

## 2. System Overview

### 2.1 Problem Statement

Wholesalers send product images and pricing via Telegram groups and channels daily. The volume across 50–60 wholesalers generates hundreds of messages per day. When a client requests a product, there is no mechanism to search this data — resulting in missed sales, delayed responses, and loss of client trust.

### 2.2 Solution

An automated ingestion pipeline that monitors admin-approved Telegram groups and channels in real time, extracts product data, generates semantic image embeddings using CLIP, and stores structured records in a dual-database architecture (PostgreSQL + Qdrant). A FastAPI layer exposes this data for search and for consumption by future modules.

### 2.3 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    TELEGRAM (Groups / Channels)                     │
│              Wholesaler A   Wholesaler B   Wholesaler N             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  MTProto (Pyrogram)
┌──────────────────────────────▼──────────────────────────────────────┐
│                   INGESTION SERVICE (Python)                        │
│    Pyrogram Listener → Whitelist Filter → Message Extractor         │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────────┐
│                   PROCESSING PIPELINE (Python)                      │
│    Image Download → CLIP Embedding → Dedup Check → Storage Write    │
└──────────┬───────────────────────────────────────┬──────────────────┘
           │                                       │
┌──────────▼──────────┐             ┌──────────────▼───────────────┐
│    PostgreSQL       │             │         Qdrant               │
│  (Structured Data)  │             │   (Vector Embeddings)        │
└──────────┬──────────┘             └─────────────┬────────────────┘
           │                                       │
┌──────────▼───────────────────────────────────────▼────────────────┐
│                   FastAPI + Uvicorn (REST API)                     │
│        Search  /  Admin  /  Webhooks  /  Module Integration        │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Technology Stack

### 3.1 Core Stack

| Component | Purpose | Layer |
|---|---|---|
| Python 3.11+ | Primary backend language. Ideal ML/async ecosystem. | Runtime |
| FastAPI | High-performance async REST framework with auto OpenAPI docs. | API Layer |
| Uvicorn | ASGI server. Production grade with worker support. | Server |
| Pyrogram | MTProto Python client. Official Telegram protocol. | Ingestion |
| CLIP (OpenAI) | Multimodal image+text embeddings for semantic search. | ML / Embeddings |
| PostgreSQL 15+ | Primary relational store. Products, wholesalers, audit logs. | Database |
| Qdrant | High-performance vector database for similarity search. | Vector DB |
| Redis | Async task queue (via ARQ). Dedup cache. Rate limiting. | Queue / Cache |
| Cloudflare R2 | S3-compatible object storage. Free tier. Image files. | Storage |
| SQLAlchemy 2 + Alembic | ORM + migration management. Industry standard. | ORM |
| Pydantic v2 | Data validation and serialisation throughout FastAPI. | Validation |
| Docker + Compose | Containerised deployment. Reproducible environments. | Infrastructure |

### 3.2 Rationale for Key Choices

#### FastAPI over Flask/Django
FastAPI provides native async support critical for Pyrogram's event loop, automatic OpenAPI documentation consumed by future module developers, and Pydantic-based request/response validation out of the box. Django's ORM is synchronous and adds unnecessary overhead for this use case.

#### Qdrant over Pinecone / Weaviate
Qdrant is self-hosted, open source, and runs efficiently on a 4GB RAM VPS. Pinecone introduces per-vector costs and external data dependency. At Buyerzone's scale (tens of thousands of products), Qdrant on Hetzner is zero marginal cost and provides sub-10ms search latency.

#### Pyrogram over python-telegram-bot
python-telegram-bot uses the Bot API which requires explicit group membership via bot invitation. Pyrogram uses MTProto and operates as a real user account — silently reading all groups and channels the account is already joined to, requiring zero coordination with wholesalers.

#### Redis + ARQ over Celery
ARQ (Async Redis Queue) is the async-native task queue built for asyncio. Celery is synchronous by design and requires significant boilerplate for async workloads. ARQ integrates naturally with FastAPI's async architecture.

---

## 4. Data Models

### 4.1 PostgreSQL Schema

#### wholesalers
```sql
CREATE TABLE wholesalers (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name          VARCHAR(255) NOT NULL,
  telegram_id   BIGINT UNIQUE,          -- Telegram user/channel ID
  telegram_username VARCHAR(100),
  phone         VARCHAR(20),
  is_active     BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);
```

#### monitored_chats (Admin Whitelist)
```sql
CREATE TABLE monitored_chats (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id       BIGINT UNIQUE NOT NULL,  -- Telegram chat ID
  chat_name     VARCHAR(255) NOT NULL,
  chat_type     VARCHAR(20) NOT NULL,    -- group | channel | supergroup
  is_active     BOOLEAN DEFAULT TRUE,
  added_by      UUID REFERENCES admin_users(id),
  added_at      TIMESTAMPTZ DEFAULT NOW()
);
```

#### products
```sql
CREATE TABLE products (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  qdrant_id       UUID UNIQUE NOT NULL,   -- Mirror of Qdrant point ID
  wholesaler_id   UUID REFERENCES wholesalers(id),
  chat_id         BIGINT REFERENCES monitored_chats(chat_id),
  telegram_msg_id BIGINT NOT NULL,
  name            VARCHAR(500),           -- Extracted or AI-inferred
  raw_caption     TEXT,                   -- Original caption as-is
  price           NUMERIC(10, 2),
  currency        VARCHAR(10) DEFAULT 'INR',
  image_url       TEXT NOT NULL,          -- Cloudflare R2 URL
  image_key       TEXT NOT NULL,          -- R2 object key
  source_platform VARCHAR(20) DEFAULT 'telegram',
  status          VARCHAR(20) DEFAULT 'active', -- active | stale | removed
  received_at     TIMESTAMPTZ NOT NULL,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_products_wholesaler  ON products(wholesaler_id);
CREATE INDEX idx_products_status       ON products(status);
CREATE INDEX idx_products_received_at  ON products(received_at DESC);
```

#### ingestion_logs (Audit Trail)
```sql
CREATE TABLE ingestion_logs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id       BIGINT NOT NULL,
  telegram_msg_id BIGINT NOT NULL,
  status        VARCHAR(20) NOT NULL,    -- processed | skipped | failed | duplicate
  reason        TEXT,                    -- Skip/fail reason
  product_id    UUID REFERENCES products(id),
  processed_at  TIMESTAMPTZ DEFAULT NOW()
);
```

### 4.2 Qdrant Collection Schema

```
Collection: product_embeddings

Vector:
  size:     512          # CLIP ViT-B/32 output dimension
  distance: Cosine       # Semantic similarity metric

Payload (mirrored from PostgreSQL for search context):
  product_id    : str    # PostgreSQL products.id
  wholesaler_id : str
  wholesaler_name: str
  price         : float
  image_url     : str
  chat_name     : str
  received_at   : str    # ISO timestamp
  status        : str
```

---

## 5. Detailed System Flow

### 5.1 Authentication Flow (One-Time Setup)

Pyrogram authenticates using MTProto, the native Telegram protocol. Authentication is a one-time operation — the session is persisted to disk and reused on every subsequent startup.

```
Step 1: Developer registers app at my.telegram.org
        → Obtains API_ID and API_HASH

Step 2: First run of ingestion service
        → Pyrogram prompts for phone number
        → Telegram sends OTP via SMS / Telegram app
        → Developer enters OTP once
        → Session file saved to /app/sessions/buyerzone.session

Step 3: All subsequent startups
        → Pyrogram loads session file
        → Connects to Telegram MTProto servers
        → No OTP required

Note: Session file must be backed up. Loss requires re-authentication.
```

### 5.2 Admin — Adding Monitored Chats

Admins interact via the Admin API to add groups/channels by name. The system resolves names to Telegram chat IDs automatically using Pyrogram.

```
Admin Request:  POST /admin/chats/search  { "name": "Buyerzone Wholesalers" }

  → Pyrogram calls iter_dialogs() to fetch all joined groups/channels
  → Filter dialogs where title contains search name (case-insensitive)
  → If 1 match:  return single result with chat_id, name, type, member_count
  → If N matches: return list for admin to select correct chat

Admin Request:  POST /admin/chats/add  { "group_name or channel_name": Buyerzone Wholesalers (case sensitive) }

  → Validate name exists in Pyrogram dialogs
  → INSERT into monitored_chats table
  → In-memory whitelist set updated immediately (no restart needed)
  → Listener begins capturing messages from this chat instantly
```

### 5.3 Ingestion Flow (Real-Time, 24/7)

```
Event: New message arrives in any Telegram chat
                 │
                 ▼
FILTER:  Is chat_id in monitored_chats whitelist?
         NO  → skipped → discard
         YES → continue
                 │
                 ▼
EXTRACT: Does message contain Words like "Stock Out" or "out of stock" or related other words?
         NO  → log as skipped (out of stock message) → discard
         YES → extract:
               - photo file_id (highest resolution)
               - caption text (may be None)
               - sender user_id
               - chat_id, chat title
               - message_id, date
                 │
                 ▼
ENQUEUE: Push MessagePayload to Redis ARQ queue
         → Ingestion listener returns immediately (non-blocking)
         → Processing happens asynchronously
```

### 5.4 Processing Pipeline (Async Workers)

```
ARQ Worker picks up MessagePayload from queue
                 │
                 ▼
DOWNLOAD: Pyrogram downloads only first image bytes via file_id
          → Validate: is it a real image? (check magic bytes)
          → Resize to 224x224 for CLIP (preserve original separately)
                 │
                 ▼
UPLOAD:   Upload original image to Cloudflare R2
          → Key format: products/{chat_id}/{msg_id}/{uuid}.jpg
          → Store public URL
                 │
                 ▼
PARSE:    Extract price from caption using regex
          Pattern: ₹\d+|Rs\.?\s*\d+|\d+\s*/-
          Extract product name: caption text minus price pattern
                 │
                 ▼
EMBED:    Run image through CLIP ViT-B/32
          → Returns 512-dimensional float32 vector
          → Normalise vector (L2 norm) for cosine similarity
                 │
                 ▼
DEDUP:    Search Qdrant for vectors with cosine similarity > 0.96
          from same wholesaler_id within last 30 days
          DUPLICATE FOUND → log as duplicate → skip insert
          NO DUPLICATE   → continue
                 │
                 ▼
PERSIST:  BEGIN transaction
          1. INSERT into products table (PostgreSQL)
          2. INSERT point into Qdrant (vector + payload)
          3. INSERT into ingestion_logs (status=processed)
          COMMIT
          ON ERROR → ROLLBACK → log as failed → push to dead-letter queue
```

### 5.5 Search Flow

```
Client/Internal Request: POST /search/image
  Body: { image: <base64> | multipart file, top_k: 10 }
                 │
                 ▼
EMBED:    Run query image through CLIP → 512-dim vector
                 │
                 ▼
SEARCH:   Qdrant similarity search
          filter: status = "active"
          top_k: 10 (configurable)
          → Returns: [ { product_id, score, payload } ]
                 │
                 ▼
ENRICH:   Fetch full product records from PostgreSQL by product_ids
          Join with wholesalers table for contact info
                 │
                 ▼
RESPOND:  Return ranked results with:
          product name, price, image_url,
          wholesaler name + contact,
          similarity score, received_at
```

---

## 6. API Specification

All endpoints are prefixed with `/api/v1`. use JWT Bearer tokens.

### 6.1 Admin Endpoints

| Endpoint | Description | Auth |
|---|---|---|
| `POST /admin/chats/search` | Search joined chats by name. Returns list of matches. | JWT Admin |
| `POST /admin/chats/add` | Add chat_id to monitored whitelist. | JWT Admin |
| `DELETE /admin/chats/{id}` | Remove chat from whitelist. Stops monitoring immediately. | JWT Admin |
| `GET /admin/chats` | List all monitored chats with status and message counts. | JWT Admin |
| `POST /admin/wholesalers` | Register a new wholesaler with Telegram ID. | JWT Admin |
| `GET /admin/wholesalers` | List all wholesalers. | JWT Admin |
| `PATCH /admin/wholesalers/{id}` | Update wholesaler info or active status. | JWT Admin |
| `GET /admin/logs` | Ingestion audit logs. Filter by date, status, chat. | JWT Admin |
| `GET /admin/stats` | Dashboard stats: products ingested, by chat, by wholesaler. | JWT Admin |

### 6.2 Search Endpoints

| Endpoint | Description | Auth |
|---|---|---|
| `POST /search/image` | Upload image, get similar products. Accepts multipart or base64. | JWT Admin |
| `GET /search/text` | Full-text search on product name. Query param: `q`. | JWT Admin |
| `POST /search/combined` | Image + text search. Weighted combination of both signals. | JWT Admin |
| `GET /products/{id}` | Fetch single product with full wholesaler details. | JWT Admin |
| `GET /products` | Paginated product list. Filter by wholesaler, chat, date range. | JWT Admin |
| `PATCH /products/{id}/status` | Mark product as stale or removed. | JWT Admin |

### 6.3 Internal / Module Integration Endpoints 

| Endpoint | Description | 
|---|---|
| `GET /internal/products/recent` | Last N products ingested. For dashboard module. | 
| `GET /internal/wholesalers/active` | Active wholesalers list. For order module. | 
| `POST /internal/products/bulk-status` | Bulk update product status. For staleness cron. |
| `GET /internal/health` | Service health: DB, Qdrant, Redis, Pyrogram session. | 

---

## 7. Project Structure

```
bz-core/
├── app/
│   ├── main.py                  # FastAPI app factory, lifespan, router registration
│   ├── config.py                # Pydantic Settings — env vars, secrets
│   │
│   ├── api/                     # Route handlers only — thin layer
│   │   └── v1/
│   │       ├── admin.py         # /admin/* routes
│   │       ├── search.py        # /search/* routes
│   │       ├── products.py      # /products/* routes
│   │       └── internal.py      # /internal/* routes
│   │
│   ├── services/                # Business logic — all heavy lifting here
│   │   ├── ingestion.py         # Pyrogram listener + message parsing
│   │   ├── processing.py        # CLIP embedding + pipeline orchestration
│   │   ├── search.py            # Qdrant search + result enrichment
│   │   ├── storage.py           # R2 upload/download abstraction
│   │   ├── chat_resolver.py     # Pyrogram dialog search + whitelist mgmt
│   │   └── staleness.py         # Cron job — mark old products stale
│   │
│   ├── models/                  # SQLAlchemy ORM models
│   │   ├── product.py
│   │   ├── wholesaler.py
│   │   ├── monitored_chat.py
│   │   └── ingestion_log.py
│   │
│   ├── schemas/                 # Pydantic request/response schemas
│   │   ├── product.py
│   │   ├── search.py
│   │   └── admin.py
│   │
│   ├── core/
│   │   ├── database.py          # SQLAlchemy async engine + session
│   │   ├── qdrant.py            # Qdrant client + collection setup
│   │   ├── redis.py             # Redis client + ARQ queue config
│   │   ├── clip.py              # CLIP model loader (singleton)
│   │   ├── security.py          # JWT auth
│   │   └── exceptions.py        # Custom exception classes
│   │
│   └── workers/
│       ├── arq_worker.py        # ARQ worker entrypoint + job definitions
│       └── tasks/
│           ├── process_message.py   # Main processing pipeline task
│           └── staleness_check.py   # Periodic staleness cron task
│
├── alembic/                     # Database migrations
│   ├── versions/
│   └── env.py
│
├── sessions/                    # Pyrogram session files (gitignored)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── pyproject.toml               # Dependencies via Poetry
└── README.md
```

---

## 8. Infrastructure & Deployment

### 8.1 Hetzner VPS Specification (Ignore for now)

| Parameter | Value |
|---|---|
| Server Type | CX21 or CX31 (minimum) |
| vCPU | 2–4 cores |
| RAM | 4GB minimum, 8GB recommended |
| Storage | 40GB SSD (OS + databases) |
| OS | Ubuntu 22.04 LTS |
| Location | Nuremberg or Helsinki |
| Monthly Cost | ~€5–€10/month |

### 8.2 Docker Compose Services

```yaml
services:

  api:                         # FastAPI + Uvicorn
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
    env_file: .env
    depends_on: [postgres, redis, qdrant]
    volumes:
      - ./sessions:/app/sessions   # Persist Pyrogram session

  worker:                      # ARQ background workers
    build: .
    command: python -m arq app.workers.arq_worker.WorkerSettings
    env_file: .env
    depends_on: [postgres, redis, qdrant]
    volumes:
      - ./sessions:/app/sessions

  ingestion:                   # Pyrogram listener (long-running)
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

volumes:
  postgres_data:
  qdrant_data:
  redis_data:
```

### 8.3 Environment Variables

```env
# Telegram
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_SESSION_NAME=buyerzone

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://buyerzone:password@postgres:5432/buyerzone

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333
QDRANT_COLLECTION=product_embeddings

# Redis
REDIS_URL=redis://redis:6379

# Cloudflare R2
R2_ACCESS_KEY_ID=your_key
R2_SECRET_ACCESS_KEY=your_secret
R2_BUCKET_NAME=buyerzone-products
R2_PUBLIC_URL=https://your-r2-domain.com

# Security
JWT_SECRET_KEY=your_256bit_secret
JWT_ALGORITHM=HS256
API_KEY=your_internal_api_key

# App
ENVIRONMENT=production
LOG_LEVEL=INFO
DEDUP_SIMILARITY_THRESHOLD=0.96
STALENESS_DAYS=60
```

---

## 9. Implementation Phases

### Phase 1 — Foundation (Week 1–2)
**Goal:** All infrastructure running, database schema deployed, Pyrogram authenticated.

1. Set up Hetzner VPS, install Docker + Compose (Avoid this)
2. Create Docker Compose with PostgreSQL, Qdrant, Redis
3. Run Alembic migrations — create all tables
4. Pyrogram first-run authentication — save session file
5. FastAPI skeleton with health check endpoint
6. Verify Pyrogram can list all joined dialogs

### Phase 2 — Ingestion Core (Week 2–3)
**Goal:** Messages from whitelisted chats are captured and queued automatically.

1. Admin API — chat search and whitelist management
2. In-memory whitelist cache updated on every admin add/remove
3. Pyrogram listener service — filter by whitelist, enqueue to Redis
4. ARQ worker setup — process_message task skeleton
5. Image download from Telegram + upload to R2
6. Ingestion logs written for every message

### Phase 3 — Processing Pipeline (Week 3–4)
**Goal:** Every ingested image gets a CLIP embedding stored in Qdrant.

1. CLIP model loaded as singleton — ViT-B/32
2. Embedding generation for downloaded images
3. Price and product name extraction from captions
4. PostgreSQL product record insertion
5. Qdrant point insertion with payload
6. Duplicate detection logic via Qdrant similarity threshold

### Phase 4 — Search API (Week 4–5)
**Goal:** Image search and text search endpoints live and tested.

1. `POST /search/image` — CLIP embed + Qdrant search + PostgreSQL enrich
2. `GET /search/text` — PostgreSQL full-text search with pg_trgm
3. `POST /search/combined` — weighted fusion of image and text scores
4. `GET /products` — paginated listing with filters
5. Performance testing: target < 500ms for image search

### Phase 5 — Hardening & Module Readiness (Week 5–6)
**Goal:** Production-ready, documented, ready for downstream module integration.

1. Wholesaler management CRUD APIs
2. Staleness cron job — mark products older than N days as stale
3. Admin dashboard stats endpoint
4. Internal module integration endpoints with service token auth
5. Error handling, dead-letter queue for failed processing jobs
6. API documentation review — OpenAPI schema clean and complete
7. Load testing with realistic message volumes

---

## 10. Security Considerations

### 10.1 Authentication Layers

| Layer | Mechanism |
|---|---|
| Admin API | JWT Bearer token. Short expiry (1week) + refresh token. |
| Search / Products API | JWT Bearer token |
| Internal Module API | Service-to-service token. Long-lived, rotated monthly. |
| Pyrogram Session | Session file stored with 600 permissions. Never in git. |

### 10.2 Data Security

- All secrets via environment variables — never hardcoded
- PostgreSQL accessible only within Docker network — not exposed externally
- Qdrant accessible only within Docker network
- Redis password-protected in production
- R2 images served via public CDN URL — no direct bucket access exposed
- Pyrogram session file excluded from version control via `.gitignore`
- Regular automated backups: PostgreSQL dump + Qdrant snapshot to R2

---

## 11. Scalability & Future Modules

### 11.1 Current Capacity Estimate

| Metric | Estimate |
|---|---|
| Messages per day | 500–1,000 (50 wholesalers × 10–20 msgs) |
| Products in catalog | ~100,000 after 1 year |
| Qdrant memory at 100k | ~200MB (512-dim float32 × 100k vectors) |
| Search latency (p99) | < 500ms including CLIP embed + Qdrant search |
| Storage (R2) at 100k | ~50GB assuming 500KB avg image size |
| VPS requirement | CX21 (4GB RAM) sufficient up to 500k products |

### 11.2 Designed for Module Expansion

This module is intentionally scoped to ingestion and search. The data it produces is the foundation for the following planned modules:

- **Analytics & Dashboard Module** — wholesaler activity trends, category breakdown, pricing intelligence, ingestion volume charts. Consumes `/internal/products/*` endpoints.
- **Order Management Module** — links client orders to specific product records and wholesaler contacts. Consumes wholesaler contact data from this module.
- **WhatsApp Ingestion Module** — parallel ingestion from WhatsApp groups via Baileys. Produces identical product records into the same PostgreSQL + Qdrant stores.
- **Client-Facing Catalog Module** — public or reseller-facing product search UI. Consumes `/search/*` endpoints.
- **Staleness Intelligence Module** — ML-based prediction of product availability based on wholesaler resend patterns.

### 11.3 Scaling Path

- Vertical scaling on Hetzner covers up to ~1M products without architectural change
- Beyond that: Qdrant supports distributed mode across multiple nodes
- ARQ workers can be scaled horizontally — run multiple worker containers
- FastAPI behind Nginx with multiple Uvicorn workers for API throughput

---

## 12. Total Cost of Ownership

| Component | Cost |
|---|---|
| Hetzner CX21 VPS | ~€5/month |
| Cloudflare R2 Storage | Free up to 10GB, ~$0.015/GB after |
| Pyrogram (MTProto) | Free — official Telegram protocol |
| CLIP Model | Free — open source, runs locally |
| Qdrant | Free — self-hosted |
| PostgreSQL | Free — self-hosted |
| Redis | Free — self-hosted |
| FastAPI / Uvicorn | Free — open source |
| **Total Monthly** | **~€5–€10/month (server only)** |

> The entire stack runs on a single Hetzner VPS with zero per-message or per-API-call fees. This architecture scales to hundreds of thousands of products before requiring any infrastructure upgrade.

---

## 13. Open Questions & Decisions Pending

| Question | Details | Recommendation | Owner's response
|---|---|---|
| AI Product Name Inference | Use GPT-4o Vision to auto-name products with no caption? | Adds ~$0.01/image API cost. Decide based on caption coverage rate. | Not needed
| Staleness Threshold | How many days before a product is marked stale? | Suggested default: 60 days. Configurable per wholesaler. | Configurable per wholesaler. default : 30 for all
| Pyrogram Account | Use personal number or dedicated business number? | Dedicated number recommended for production. | already have dedicated business number
| Price Currency | All wholesalers price in INR? | Confirm. If multi-currency, add currency detection to parser. | INR only
| Search Result Limit | Default top_k for image search? | Suggested: 10. Make configurable via query param. | Make configurable via query param , default : 10

---

*Buyerzone Catalog Intelligence System — Telegram Ingestion Module — v1.0 — Confidential*


uvicorn app.main:app --reload --port 8000
python -m arq app.workers.arq_worker.WorkerSettings
python -m app.services.ingestion