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
