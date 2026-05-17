"""Centralised structlog configuration.

Import this module once at each process entrypoint (main.py, ingestion.py,
arq_worker.py) before any logger is instantiated.  It adds the ``"level"``
field to every JSON log record so log viewers (Grafana Loki, Datadog, etc.)
can classify entries instead of showing "Unknown".
"""
from __future__ import annotations

import structlog


def configure_logging() -> None:
    """Configure structlog globally.  Safe to call multiple times (idempotent)."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,           # injects "level" key
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),      # compact JSON lines
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )
