# BuyerZone Catalog

B2B Catalog Intelligence System — Telegram Ingestion Module for a dropshipping intermediary platform.

Ingests product listings from Telegram wholesaler groups, generates CLIP embeddings for visual similarity search, and exposes REST APIs for downstream modules (dashboard, order management, client catalog).

## Tech Stack

- **Runtime:** Python 3.11+, FastAPI + Uvicorn
- **Telegram:** Pyrogram (MTProto client)
- **ML:** CLIP ViT-B/32 for 512-dim image embeddings
- **Databases:** PostgreSQL 15+ (SQLAlchemy 2.0), Qdrant (vectors), Redis (queue)
- **Task Queue:** ARQ (async Redis-based workers)
- **Storage:** Cloudflare R2 (S3-compatible)

## Quick Start

```bash
poetry install
cp .env.example .env  # fill in credentials

alembic upgrade head
uvicorn app.main:app --reload
python -m arq app.workers.arq_worker.WorkerSettings
python -m app.services.ingestion
```

## Docker

```bash
docker compose up
```

## Environment Variables

See `.env.example` for all required variables.
