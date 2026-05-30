# Stage 1: Builder — installs all deps
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev libssl-dev libjpeg-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN pip install --no-cache-dir poetry==1.8.4

# Copy dependency manifests only — enables Docker layer caching
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.create false \
    && poetry install --without dev --no-interaction --no-ansi

# Stage 2: Runtime — lean final image
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev zlib1g-dev libssl-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r app && useradd -r -g app -s /bin/false app

WORKDIR /app

# Copy installed packages from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Pre-bake CLIP weights so worker cold-starts are instant (~350 MB, cached layer)
# Must run before COPY . . so source changes don't bust this layer
ENV HF_HOME=/app/.cache
ENV TORCH_HOME=/app/.cache
RUN mkdir -p /app/.cache \
    && python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-16-SigLIP', pretrained='webli'); open_clip.get_tokenizer('ViT-B-16-SigLIP')"

# Copy application source
COPY . .

USER app

EXPOSE 8000

# Health check — FastAPI must expose GET /health
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
