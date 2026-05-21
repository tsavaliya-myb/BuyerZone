FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# VITE_API_URL is baked into the JS bundle at build time.
# It's always /api/v1 (relative path — the Express server proxies it).
ENV VITE_API_URL=/api/v1

RUN npm run build

# ── Runtime ──────────────────────────────────────────────────────────────────
FROM node:20-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

COPY --from=builder /app/dist ./dist
COPY server.js ./

EXPOSE 10000

CMD ["node", "server.js"]
