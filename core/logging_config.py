import os
import logging
import contextvars
from logging.config import dictConfig


class ChannelAliasFilter(logging.Filter):
    """Adds a friendly channel name to log records.

    Example mappings:
    - uvicorn.error -> uvicorn
    - celery.app.trace -> celery
    Other names pass through unchanged.
    """

    NAME_MAP = {
        "uvicorn.error": "uvicorn",
        "uvicorn.access": "uvicorn.access",
        "celery.app.trace": "celery",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        record.channel = self.NAME_MAP.get(record.name, record.name)
        return True


# Trace context
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_ctx.get() or "-"
        return True


def _resolve_log_level(default: str = "INFO") -> str:
    # Single source of truth: LOGS_LEVEL
    env_level = os.getenv("LOGS_LEVEL", "").strip().upper()
    if env_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return env_level
    return default


def configure_logging() -> None:
    """Configure application-wide logging using stdlib logging.

    - Single console handler suitable for Dozzle (plain text, no JSON)
    - Unify levels across app, uvicorn and celery
    - Keep existing loggers (disable_existing_loggers=False)
    """
    level = _resolve_log_level()

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "channel": {"()": "core.logging_config.ChannelAliasFilter"},
            "trace": {"()": "core.logging_config.TraceIdFilter"},
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)s | %(channel)s | trace=%(trace_id)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # Uvicorn access logs are very chatty; keep them concise
            "uvicorn_access": {
                "format": "%(asctime)s | %(levelname)s | %(channel)s | trace=%(trace_id)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": level,
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "uvicorn_console": {
                "class": "logging.StreamHandler",
                "formatter": "uvicorn_access",
                "level": level,
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
        },
        "loggers": {
            # App-level
            "": {  # root
                "handlers": ["console"],
                "level": level,
            },
            # Uvicorn loggers
            "uvicorn": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["uvicorn_console"],
                "level": level,
                "propagate": False,
            },
            # Celery loggers
            "celery": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
            "celery.app.trace": {
                "handlers": ["console"],
                "level": level,
                "propagate": False,
            },
        },
    }

    dictConfig(config)
    logging.getLogger(__name__).debug("Logging configured with level %s", level)


