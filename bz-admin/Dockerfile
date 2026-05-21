FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Baked into the JS bundle at build time — /api/v1 is a relative path,
# nginx proxies it to the API container.
ENV VITE_API_URL=/api/v1

RUN npm run build

# ── Runtime — lightweight Nginx to serve static files + proxy API ────────────
FROM nginx:alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
