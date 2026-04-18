# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BuyerZone** is a B2B Catalog Intelligence System — a Telegram Ingestion Module for a dropshipping intermediary platform. It ingests product listings from Telegram wholesaler groups, generates CLIP embeddings for visual similarity search, and exposes REST APIs for downstream modules (dashboard, order management, client catalog).

The full implementation spec is at [Buyerzone_Telegram_Implementation.md](Buyerzone_Telegram_Implementation.md).

## Tech Stack

- **Runtime:** Python 3.11+, FastAPI + Uvicorn (ASGI)
- **Telegram:** Pyrogram (MTProto client)
- **ML:** CLIP ViT-B/32 (OpenAI) for 512-dim image embeddings
- **Databases:** PostgreSQL 15+ (asyncpg/SQLAlchemy 2.0), Qdrant (vectors), Redis (queue)
- **Task Queue:** ARQ (async Redis-based workers)
- **ORM/Migrations:** SQLAlchemy 2.0 + Alembic
- **Validation:** Pydantic v2
- **Storage:** Cloudflare R2 (S3-compatible image storage)
- **Infra:** Docker Compose on Hetzner VPS

## Commands

Once `pyproject.toml` is set up with Poetry:

```bash
poetry install                                          # Install dependencies
uvicorn app.main:app --reload                           # Dev API server
python -m arq app.workers.arq_worker.WorkerSettings     # Start async workers
python -m app.services.ingestion                        # Start Telegram listener
alembic upgrade head                                    # Run DB migrations
alembic revision --autogenerate -m "<msg>"              # Generate migration

# Quality
ruff check .
black .
mypy .
pytest
pytest tests/path/test_file.py::test_name -v            # Single test

# Docker (all services)
docker compose up
docker compose down
```

## Architecture

The system is an **event-driven async pipeline**:

```
Telegram Groups/Channels
    ↓  Pyrogram listener (app/services/ingestion.py)
Redis ARQ Task Queue
    ↓  Async workers (app/workers/)
Processing Pipeline
    - Image download + validation
    - CLIP embedding (512-dim)
    - Dedup check (cosine similarity > 0.96 within 30 days)
    - Atomic write to PostgreSQL + Qdrant
    ↓
FastAPI REST API (app/api/v1/)
    ↓
Downstream modules
```

### Project Structure

```
buyerzone-catalog/
├── app/
│   ├── main.py                  # FastAPI app factory, lifespan, router registration
│   ├── config.py                # Pydantic Settings — env vars, secrets
│   ├── api/v1/
│   │   ├── admin.py             # /admin/* routes
│   │   ├── search.py            # /search/* routes
│   │   ├── products.py          # /products/* routes
│   │   └── internal.py          # /internal/* routes
│   ├── services/
│   │   ├── ingestion.py         # Pyrogram listener + message parsing
│   │   ├── processing.py        # CLIP embedding + pipeline orchestration
│   │   ├── search.py            # Qdrant search + result enrichment
│   │   ├── storage.py           # R2 upload/download abstraction
│   │   ├── chat_resolver.py     # Pyrogram dialog search + whitelist mgmt
│   │   └── staleness.py         # Cron job — mark old products stale
│   ├── models/                  # SQLAlchemy ORM: product, wholesaler, monitored_chat, ingestion_log
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── core/
│   │   ├── database.py          # SQLAlchemy async engine + session
│   │   ├── qdrant.py            # Qdrant client + collection setup
│   │   ├── redis.py             # Redis client + ARQ queue config
│   │   ├── clip.py              # CLIP model loader (singleton)
│   │   ├── security.py          # JWT auth
│   │   └── exceptions.py        # Custom exception classes
│   └── workers/
│       ├── arq_worker.py        # ARQ worker entrypoint + job definitions
│       └── tasks/
│           ├── process_message.py   # Main processing pipeline task
│           └── staleness_check.py   # Periodic staleness cron task
├── alembic/versions/            # Database migrations
├── sessions/                    # Pyrogram session files (gitignored)
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── pyproject.toml
```

### Dual Storage Pattern

Every product write is an **atomic two-phase commit**:
1. Insert/update row in PostgreSQL (`products` table) to get `product_id`
2. Upsert vector in Qdrant (`product_embeddings` collection) with `product_id` as payload

Rollback both on any failure — partial writes are not acceptable.

### Dedup Logic

Before inserting, query Qdrant for vectors with cosine similarity > 0.96 from the same wholesaler within the last 30 days. If found, log as duplicate in `ingestion_logs` and skip.

## Environment Variables

```
TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION_NAME
DATABASE_URL                          # asyncpg-format postgres URL
QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION
REDIS_URL
R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME
JWT_SECRET_KEY, JWT_ALGORITHM
ENVIRONMENT, LOG_LEVEL
DEDUP_SIMILARITY_THRESHOLD            # default 0.96
STALENESS_DAYS                        # default 30
```

## API Structure

All routes are JWT-protected (Bearer token). Two auth tiers:
- **Admin APIs** (`/admin/`) — chat whitelist management, stats
- **Search APIs** (`/search/`) — image similarity, text, combined weighted search
- **Product APIs** (`/products/`) — paginated listing with filters
- **Internal APIs** (`/internal/`) — consumed by other BuyerZone modules (no user-facing auth)

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
