from app.services.processing import process_message as _process


async def process_message(ctx: dict, payload: dict) -> None:
    """ARQ task — called by the worker for each queued Telegram message."""
    await _process(payload)
