from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class BuyerzoneError(Exception):
    """Base application error."""


class ChatNotFoundError(BuyerzoneError):
    pass


class DuplicateProductError(BuyerzoneError):
    pass


class StorageUploadError(BuyerzoneError):
    pass


class EmbeddingError(BuyerzoneError):
    pass


class ProcessingError(BuyerzoneError):
    pass


# FastAPI exception handlers

async def buyerzone_exception_handler(request: Request, exc: BuyerzoneError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "type": type(exc).__name__},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )
