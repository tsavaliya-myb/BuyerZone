 ---
  Private S3 Image Display — Full Architecture
                                                                                                                                                                                                                     Storage: iDrive E2 (S3-compatible)
                                                                                                                                                                                                                     Not AWS S3 — it's iDrive E2, an S3-compatible object storage. The bucket is fully private (no public access). The s3Client in CouponAPI/src/config/s3.ts connects to it using:
  - @aws-sdk/client-s3 with forcePathStyle: true
  - Custom endpoint: https://s3.<region>.idrivee2.com

  ---
  Upload Flow (Flutter → S3, no server buffering)

  2-step presign → confirm pattern:

  1. Flutter calls POST /sellers/me/logo/presign with the MIME type
  2. API generates a short-lived presigned PUT URL (5 min TTL) via getPresignedUploadUrl() in s3.ts, returns it to Flutter
  3. Flutter uploads the file directly to iDrive E2 using that presigned URL (bypasses the server completely)
  4. Flutter calls POST /sellers/me/logo/confirm with the fileKey
  5. API stores the permanent proxy URL (<API_BASE_URL>/media/<fileKey>) in the DB via updateSellerLogo()

  The old upload.ts middleware that passed files through the server was deprecated and replaced with this pattern.

  ---
  Serving Images: API Media Proxy

  CouponAPI/src/modules/media/media.routes.ts — a public route with no auth:

  GET /media/logos/filename.jpeg
  GET /media/photos/filename.jpeg
  GET /media/videos/filename.mp4

  What it does:
  - Validates the folder is in ALLOWED_FOLDERS (logos, photos, videos) — prevents path traversal
  - Calls GetObjectCommand on the private S3 bucket
  - Streams the S3 response body directly to the HTTP response (no memory buffering)
  - Sets Cache-Control: public, max-age=86400, immutable (24h browser cache)
  - The bucket stays 100% private — the API is the only thing that ever talks to S3

  URLs stored in the DB are permanent proxy URLs: https://api.yourdomain.com/media/logos/uuid.jpeg — they never expire.

  ---
  Cloudflare Layer (CDN Cache)

  Cloudflare sits in front of the API server as a CDN. Setup:

  1. Add domain to Cloudflare → point DNS CNAME api → <your-render/vps-host> with orange cloud (proxied)
  2. Create a Cache Rule in Cloudflare dashboard:
    - Condition: URL path starts with /media/
    - Cache: Eligible for cache ✅
    - Edge TTL: 1 day

  Result: first request for an image hits the API → API fetches from S3 → Cloudflare caches it at the edge. Every subsequent request for that image is served from Cloudflare's 300+ edge locations with zero
  server load.

  ---
  Flutter Side (Display)

  Flutter uses cached_network_image package and just loads the permanent proxy URL directly:

  // seller_card.dart, seller_detail_screen.dart
  CachedNetworkImage(
    imageUrl: logoUrl!,  // e.g. "https://api.yourdomain.com/media/logos/uuid.jpeg"
    ...
  )

  No auth headers needed on the image URL — the /media/* route is public. CachedNetworkImage also adds a disk cache layer on the device.

  ---
  Key Packages

  API (Node.js):
  - @aws-sdk/client-s3 — S3 client
  - @aws-sdk/s3-request-presigner — presigned URL generation

  Flutter:
  - cached_network_image — network image loading with disk cache

  ---
  To Replicate in Another Project

  1. API config/s3.ts — S3 client + getPublicUrl() + getPresignedUploadUrl() + extractKeyFromProxyUrl()
  2. modules/media/media.routes.ts — streaming proxy route, mount at /media in app.ts
  3. Upload endpoints — POST /presign → return presigned PUT URL; POST /confirm → store proxy URL in DB
  4. Flutter — add cached_network_image, presign → direct PUT upload → confirm flow, display with CachedNetworkImage(imageUrl: proxyUrl)
  5. Cloudflare — add domain, Cache Rule for /media/* with 1-day TTL, point DNS to your server



Phase 0 — Prep (no code changes)
Tag current state. git tag pre-restructure and push. Free rollback point.
Snapshot VPS volumes. Back up postgres_data, qdrant_data, redis_data, sessions/ to R2. You'll thank yourself if anything goes sideways.
Decide repo strategy. Confirm: stay monorepo, sibling top-level dirs (bz-core/, wa-listener/, admin-ui/, infra/). No git history rewrites.
Phase 1 — Restructure repo (low risk, no behavior change)
Move compose files. git mv bz-core/docker-compose.yml infra/ and same for docker-compose.prod.yml. Update build context: build: . → build: ../bz-core. Update volume paths: ./sessions → ../bz-core/sessions.
Update deploy.yml:197. Change cd bz-core → cd infra. Verify deploy still works end-to-end on a small no-op commit before moving on.
Move docs. git mv Buyerzone_*.md docs/. Update CLAUDE.md reference.
This phase is purely mechanical. Ship it. Verify nothing broke.

Phase 2 — Fix the slow build (do this before adding services)
Pre-bake CLIP weights in Dockerfile (the RUN python -c "..." I showed earlier). Test build time locally.
Add BuildKit cache mount for pip if you're not using one. Optional but big win.
Decide GHCR vs VPS-build now. My recommendation: stay on VPS-build for now since you said it's working and you have 16 GB RAM — the OOM concern doesn't apply. Revisit when you add the second service.
Phase 3 — WhatsApp listener (the actual new feature)
Scaffold wa-listener/ at repo root per WhatsApp spec §7.1. TypeScript + Baileys + ioredis + Express.
Define the shared payload contract. Create packages/message-payload.schema.json. Generate Pydantic model on Python side, TypeScript types on Node side. Single source of truth for the queue contract.
Alembic migration: add platform column to monitored_chats, change chat_id to TEXT (per spec §4.1). Apply on staging first.
Build out wa-listener in spec phases 1–4 (auth → whitelist → message handler → queue push). Each phase is independently testable.
Add wa_listener service to infra/docker-compose.prod.yml. Internal port 3001, no external expose, mount wa_sessions volume.
Modify process_message.py to handle image_data_b64 branch. This is the only Python change needed for WA ingestion.
Add /admin/whatsapp/* FastAPI routes that proxy to the listener's /wa-internal/*.
End-to-end test on staging: post image to a test WA group → verify product in Postgres + Qdrant.
Phase 4 — Admin UI (parallelizable with Phase 3)
Scaffold admin-ui/ with Vite + React. Point at https://api.buyerzone.xyz for dev.
Build minimum screens: login (JWT), Telegram chat management, WhatsApp pairing flow + chat management, products list, search.
Add Caddy/Nginx route for admin.buyerzone.xyz → static files. Build artifacts go in infra/admin-dist/ mounted into the proxy.
CI workflow .github/workflows/admin-ui.yml with path filter admin-ui/**. Just builds, rsync's dist/ to VPS.
Phase 5 — Operational cleanup
Per-service CI workflows with path filters so a UI change doesn't rebuild Python.
Add mem_limit: to each compose service. Prevents one runaway from killing the others.
Backup cron — restic snapshot of all named volumes + wa_sessions/ to R2 nightly.
Monitoring — at minimum, uptime check on /health and a Discord/Slack webhook for ARQ DLQ growth.