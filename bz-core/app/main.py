from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.database import engine
from app.core.exceptions import BuyerzoneError, buyerzone_exception_handler
from app.core.qdrant import close_qdrant_client, ensure_collection
from app.core.redis import close_arq_pool, close_redis

from app.core.logging_config import configure_logging

configure_logging()

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("startup_begin", environment=settings.environment)

    # Ensure Qdrant collection exists
    await ensure_collection()
    log.info("qdrant_collection_ready", collection=settings.qdrant_collection)

    # Hydrate in-memory whitelist from DB
    from app.services.chat_resolver import load_whitelist_from_db

    await load_whitelist_from_db()

    # Pre-warm CLIP model so first search request doesn't pay model-load latency
    import asyncio

    from app.core.clip import _load as clip_load

    await asyncio.get_running_loop().run_in_executor(None, clip_load)
    log.info("clip_model_warmed")

    log.info("startup_complete")
    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await close_qdrant_client()
    await close_arq_pool()
    await close_redis()
    await engine.dispose()
    log.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="BuyerZone Catalog Intelligence API",
        description="Telegram Ingestion Module — product search and admin APIs",
        version="1.0.0",
        docs_url="/docs",  # if not settings.is_production else None,
        redoc_url="/redoc",  # if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    app.add_exception_handler(BuyerzoneError, buyerzone_exception_handler)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request, exc):
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    from app.api.v1.admin import router as admin_router
    from app.api.v1.internal import router as internal_router
    from app.api.v1.media import router as media_router
    from app.api.v1.products import router as products_router
    from app.api.v1.search import router as search_router
    from app.api.v1.telegram_auth import router as telegram_auth_router
    from app.api.v1.whatsapp_admin import router as whatsapp_admin_router

    app.include_router(media_router)  # public, no prefix, no auth

    prefix = "/api/v1"
    app.include_router(admin_router, prefix=prefix)
    app.include_router(telegram_auth_router, prefix=prefix)
    app.include_router(whatsapp_admin_router, prefix=prefix)
    app.include_router(search_router, prefix=prefix)
    app.include_router(products_router, prefix=prefix)
    app.include_router(internal_router, prefix=prefix)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()
