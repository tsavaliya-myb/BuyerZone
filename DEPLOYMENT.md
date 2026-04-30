# 🚀 BuyerZone — Hostinger VPS Deployment & CI/CD Plan

## Overview

| Item | Detail |
|------|--------|
| **VPS** | Hostinger KVM 4 — 4 vCPU, 16 GB RAM, 200 GB NVMe, 16 TB BW |
| **Stack** | FastAPI + Uvicorn · PostgreSQL 15 · Qdrant · Redis · ARQ worker · Pyrogram ingestion |
| **Container runtime** | Docker + Docker Compose |
| **Reverse proxy** | Nginx (on host) |
| **Registry** | GitHub Container Registry (GHCR) — free with your GitHub account |
| **CI/CD** | GitHub Actions |
| **TLS** | Let's Encrypt via Certbot |

## Files Created / Modified

| File | Status | Purpose |
|------|--------|---------|
| `buyerzone-catalog/Dockerfile` | **Updated** | Multi-stage build, non-root user, health check |
| `buyerzone-catalog/docker-compose.prod.yml` | **New** | Production compose — pulls from GHCR, no exposed DB ports |
| `.github/workflows/deploy.yml` | **New** | Full CI/CD pipeline (lint → build → deploy) |
| `scripts/vps-setup.sh` | **New** | One-time VPS bootstrap script |

---

## Phase 1 — VPS Initial Setup (one-time, manual)

> SSH into your VPS as **root** first. All subsequent deployments are handled automatically by GitHub Actions.

### Step 1.1 — Run the bootstrap script

> The fresh VPS has nothing on it. This script installs Docker (to run containers), Nginx (to handle HTTPS traffic), Certbot (for SSL), a firewall (UFW), Fail2Ban (to block brute-force SSH attacks), and 4 GB of swap space (safety net when CLIP loads the ML model into RAM).

```bash
# From your local machine — upload and run
scp scripts/vps-setup.sh root@YOUR_VPS_IP:/root/
ssh root@YOUR_VPS_IP "bash /root/vps-setup.sh"
```

### Step 1.2 — Copy your SSH key to the deploy user

> The bootstrap script creates a non-root `deploy` user. You'll log in as this user from now on — root access is locked down. You need your SSH key on it so GitHub Actions (and you) can connect without a password.

```bash
# For your own access
ssh-copy-id -i ~/.ssh/id_rsa.pub deploy@YOUR_VPS_IP

# For CI/CD — generate a separate key with no passphrase so GitHub can use it unattended
ssh-keygen -t ed25519 -f ~/.ssh/buyerzone_deploy -N ""
ssh-copy-id -i ~/.ssh/buyerzone_deploy.pub deploy@YOUR_VPS_IP
# Keep buyerzone_deploy (private) — you'll add it to GitHub Secrets later
```

### Step 1.3 — Clone the repo on VPS

> The VPS needs a local copy of the repo so it can pick up `docker-compose.prod.yml` updates and run `git pull` during each deployment.

```bash
ssh deploy@YOUR_VPS_IP
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/YOUR_ORG/BuyerZone.git
cd BuyerZone/buyerzone-catalog
```

### Step 1.4 — Create the production `.env`

> This file holds all your secrets (DB passwords, API keys, tokens). It is **never committed to git** — it lives only on the server. Each service reads it at startup via `env_file: .env` in the compose file.

```bash
cp .env.example .env
nano .env
```

Fill in these values (generate passwords with `openssl rand -hex 32`):

```env
ENVIRONMENT=production
LOG_LEVEL=INFO

# Strong random strings — generate with: openssl rand -hex 32
DB_PASSWORD=<strong-random>
JWT_SECRET_KEY=<strong-random>
INTERNAL_API_KEY=<strong-random>
REDIS_PASSWORD=<strong-random>

# Use Docker service names as hostnames — containers talk to each other by service name
DATABASE_URL=postgresql+asyncpg://buyerzone:<DB_PASSWORD>@postgres:5432/buyerzone
QDRANT_HOST=qdrant
QDRANT_PORT=6333
REDIS_URL=redis://:<REDIS_PASSWORD>@redis:6379

# From your Telegram API dashboard (my.telegram.org)
TELEGRAM_API_ID=your_id
TELEGRAM_API_HASH=your_hash
TELEGRAM_SESSION_NAME=buyerzone

# From your Cloudflare R2 dashboard
S3_ACCESS_KEY_ID=your_r2_key
S3_SECRET_ACCESS_KEY=your_r2_secret
S3_BUCKET_NAME=buyerzone-products
S3_PUBLIC_URL=https://your-r2-domain.com
S3_ENDPOINT_URL=https://your_account_id.r2.cloudflarestorage.com
S3_REGION=auto
```

### Step 1.5 — Generate Telegram Session (one-time interactive)

> Pyrogram (the Telegram MTProto client) requires a `.session` file that is created by logging in interactively with your phone number and OTP — just like signing into Telegram. This only needs to happen once. The file is then persisted in `./sessions/` which all three app containers mount as a volume.

```bash
docker compose -f docker-compose.prod.yml run --rm ingestion python -c "
from pyrogram import Client
import asyncio, os

async def main():
    app = Client(
        os.environ['TELEGRAM_SESSION_NAME'],
        api_id=int(os.environ['TELEGRAM_API_ID']),
        api_hash=os.environ['TELEGRAM_API_HASH'],
        workdir='/app/sessions'
    )
    await app.start()
    print('Session created successfully!')
    await app.stop()

asyncio.run(main())
"
```

---

## Phase 2 — First Manual Deploy

> Before CI/CD takes over, you start everything manually the first time. This also lets you verify the setup is correct before automating it.

```bash
cd ~/apps/BuyerZone/buyerzone-catalog

# Pull and start all containers (postgres, qdrant, redis, api, worker, ingestion)
docker compose -f docker-compose.prod.yml up -d

# Apply all Alembic migrations to create DB tables
# Always run this after starting — it's idempotent (safe to run multiple times)
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head

# Create the first admin user in the database
docker compose -f docker-compose.prod.yml run --rm api python seed_admin.py

# Confirm all 6 services are running
docker compose -f docker-compose.prod.yml ps

# Watch live logs to verify no startup errors
docker compose -f docker-compose.prod.yml logs -f api
```

---

## Phase 3 — Nginx Configuration

> Docker exposes the API only on `127.0.0.1:8000` (localhost only). Nginx sits in front of it as a reverse proxy — it handles HTTPS termination, SSL certificates, rate limiting, and security headers, then forwards clean HTTP traffic to the API container.

### Step 3.1 — Create the Nginx site config

```bash
sudo nano /etc/nginx/sites-available/buyerzone
```

Paste this (replace `api.yourdomain.com` with your actual domain):

```nginx
# Redirect all HTTP to HTTPS
server {
    listen 80;
    server_name api.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL cert files — created by Certbot in the next step
    ssl_certificate     /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    include             /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam         /etc/letsencrypt/ssl-dhparams.pem;

    # Prevent clickjacking, MIME sniffing, XSS attacks
    add_header X-Frame-Options           DENY;
    add_header X-Content-Type-Options    nosniff;
    add_header X-XSS-Protection          "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Rate limit: max 20 requests/sec per IP, burst of 50
    limit_req_zone $binary_remote_addr zone=api:10m rate=20r/s;
    limit_req zone=api burst=50 nodelay;

    location / {
        # Forward to the FastAPI container on localhost
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        client_max_body_size 50M;   # Allow large image uploads
    }

    # Health check endpoint — no access logging to avoid log spam
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/buyerzone /etc/nginx/sites-enabled/

# Test config syntax before applying
sudo nginx -t

# Apply
sudo systemctl reload nginx
```

### Step 3.2 — SSL Certificate

> Certbot automatically provisions a free Let's Encrypt SSL certificate and configures Nginx to use it. The `--nginx` flag patches the Nginx config automatically.

```bash
sudo certbot --nginx -d api.yourdomain.com \
  --non-interactive --agree-tos -m your@email.com
```

> Certificates expire every 90 days. Add a cron job to auto-renew them:

```bash
# Add via: crontab -e
0 3 * * * certbot renew --quiet && systemctl reload nginx
```

---

## Phase 4 — GitHub Secrets Setup

> GitHub Actions needs credentials to SSH into your VPS and push/pull Docker images. These are stored as encrypted secrets in your repo — never visible in logs.

Go to: **GitHub Repo → Settings → Secrets and Variables → Actions → New repository secret**

| Secret Name | Value | Why needed |
|-------------|-------|-----------|
| `VPS_HOST` | Your Hostinger VPS IP | To know which server to SSH into |
| `VPS_USER` | `deploy` | The non-root user to SSH as |
| `VPS_SSH_KEY` | Contents of `~/.ssh/buyerzone_deploy` | To authenticate SSH without a password |
| `VPS_APP_DIR` | `/home/deploy/apps/BuyerZone/buyerzone-catalog` | The directory to deploy into on the server |

> `GITHUB_TOKEN` is injected automatically by GitHub Actions — no need to add it.

**One more thing:** Enable write permissions for Actions so it can push to GHCR:
**Repo → Settings → Actions → General → Workflow permissions → Read and write permissions ✓**

---

## Phase 5 — GitHub Actions CI/CD Pipeline

> Every `git push` to `main` triggers the pipeline automatically. PRs only run tests (no deploy).

### Pipeline Flow

```
git push to main
        │
        ▼
┌────────────────────────────────────┐
│  Job 1: test                       │
│  Spins up postgres + redis in CI   │
│  Runs: ruff, black, pytest --cov   │
│  Must pass before anything builds  │
└─────────────────┬──────────────────┘
                  │ all tests pass
                  ▼
┌────────────────────────────────────┐
│  Job 2: build                      │
│  Multi-stage Docker build          │
│  Pushes to GHCR with two tags:     │
│    :sha-abc1234  (this exact commit)│
│    :latest       (always newest)   │
└─────────────────┬──────────────────┘
                  │ image pushed
                  ▼
┌────────────────────────────────────┐
│  Job 3: deploy (SSH to VPS)        │
│  1. git pull  → get latest compose │
│  2. docker pull new image          │
│  3. alembic upgrade head           │
│     ↑ migrations BEFORE traffic    │
│  4. docker compose up -d           │
│     (rolling — only api/worker/    │
│      ingestion, DBs untouched)     │
│  5. /health check — 5 retries      │
│  6. auto-rollback to :latest       │
│     if health check fails          │
│  7. prune images older than 72h    │
└────────────────────────────────────┘
```

### Required: Add `/health` endpoint to FastAPI

> The rollback logic pings this endpoint after every deploy. If it doesn't return 200, the pipeline rolls back to the previous image. Add it to `app/main.py` if it doesn't exist:

```python
@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok"}
```

### Required: Update image name in `docker-compose.prod.yml`

> Replace `your-org` with your actual GitHub username or organization:

```yaml
image: ghcr.io/YOUR_ACTUAL_GITHUB_USERNAME/buyerzone-catalog:${IMAGE_TAG:-latest}
```

---

## Phase 6 — Monitoring & Maintenance

### Useful shell aliases (add to `~/.bashrc` on VPS)

> Saves you from typing the long compose command every time.

```bash
alias bz='docker compose -f ~/apps/BuyerZone/buyerzone-catalog/docker-compose.prod.yml'

# Then use:
# bz ps               → show status of all 6 services
# bz logs -f api      → stream API logs
# bz logs -f ingestion → watch Telegram listener
# bz restart api      → restart just the API (no downtime for DBs)
# bz exec api bash    → open a shell inside the container
```

### PostgreSQL daily backup

> Qdrant vector data can be re-indexed from scratch, but PostgreSQL holds your core product/wholesaler data — back it up daily.

```bash
# Add via: crontab -e  (as deploy user)

# Backup at 2 AM
0 2 * * * docker exec $(docker ps -qf name=postgres) \
  pg_dump -U buyerzone buyerzone | gzip \
  > ~/backups/buyerzone_$(date +\%Y\%m\%d).sql.gz

# Delete backups older than 7 days to save disk space
0 3 * * * find ~/backups -name "*.sql.gz" -mtime +7 -delete
```

### Resource usage on your KVM 4 (16 GB RAM)

> CLIP model is the heaviest component — it loads into the ARQ worker process on startup.

| Service | RAM estimate |
|---------|-------------|
| FastAPI — 4 Uvicorn workers | ~400 MB |
| ARQ Worker (CLIP loaded) | ~800 MB |
| Pyrogram ingestion listener | ~150 MB |
| PostgreSQL 15 | ~400 MB |
| Qdrant | ~500 MB |
| Redis | ~100 MB |
| OS + Docker overhead | ~500 MB |
| **Total** | **~2.85 GB of 16 GB** |

You have ~13 GB headroom — comfortable even during model loading spikes.

---

## Final Checklist

### VPS Setup
- [ ] Run `scripts/vps-setup.sh` as root
- [ ] Copy SSH key to `deploy` user (personal + CI/CD deploy key)
- [ ] Clone repo to `~/apps/BuyerZone`
- [ ] Fill in `.env` with real secrets
- [ ] Generate Telegram session (interactive, one-time)
- [ ] Start services: `docker compose -f docker-compose.prod.yml up -d`
- [ ] Run migrations: `alembic upgrade head`
- [ ] Seed admin user: `python seed_admin.py`
- [ ] Configure Nginx site
- [ ] Get SSL cert via Certbot
- [ ] Set up backup cron

### GitHub CI/CD
- [ ] Add `GET /health` endpoint to FastAPI app
- [ ] Update `GHCR_OWNER` in `docker-compose.prod.yml`
- [ ] Add GitHub Secrets: `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY`, `VPS_APP_DIR`
- [ ] Enable Actions write permissions in repo settings
- [ ] Push to `main` → verify Actions tab runs all 3 jobs green

### Post-Deploy Verification
- [ ] `curl https://api.yourdomain.com/health` → `{"status":"ok"}`
- [ ] `bz ps` → all 6 services show `Up`
- [ ] `bz logs -f ingestion` → Telegram listener is active
- [ ] Test a JWT-protected endpoint with a Bearer token
