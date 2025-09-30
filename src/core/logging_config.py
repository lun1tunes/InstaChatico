import os
import logging
import contextvars
from logging.config import dictConfig
from core.services.telegram_alert_service import TelegramAlertService
from datetime import datetime
import json
import urllib.request
from core.config import settings
import sys
import urllib.error


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
trace_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trace_id", default=None
)


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_ctx.get() or "-"
        return True


class TelegramLogHandler(logging.Handler):
    def __init__(self, level: int = logging.WARNING):
        super().__init__(level)
        self._svc = TelegramAlertService(alert_type="app_logs")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            trace_id = getattr(record, "trace_id", "-")
            when = datetime.utcfromtimestamp(record.created).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            raw_msg = self.format(record)
            details = ""
            if record.exc_info:
                details = self.formatException(record.exc_info)
            # Prefer a synchronous send to avoid losing alerts when event loops close
            url = (
                f"https://api.telegram.org/bot{settings.telegram.bot_token}/sendMessage"
            )

            def esc(text: str) -> str:
                return (
                    text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )

            is_error = record.levelno >= logging.ERROR
            if is_error:
                # Plain-text, no thread routing for ERROR/CRITICAL
                msg_pt = raw_msg[:3500]
                det_pt = details[:3500] if details else ""
                text = (
                    f"APP LOG ALERT\n\n"
                    f"Level: {record.levelname}\n"
                    f"Logger: {record.name}\n"
                    f"Trace: {trace_id}\n"
                    f"Time: {when}\n\n"
                    f"Message:\n{msg_pt}"
                )
                if det_pt:
                    text += f"\n\nDetails:\n{det_pt}"
                payload = {
                    "chat_id": settings.telegram.chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                }
            else:
                # WARNING: HTML + thread
                safe_msg = esc(raw_msg)[:4000]
                safe_details = esc(details)[:4000] if details else ""

                text_parts = [
                    "⚠️ <b>APP LOG ALERT</b>",
                    f"<b>Level:</b> {esc(record.levelname)}",
                    f"<b>Logger:</b> {esc(record.name)}",
                    f"<b>Trace:</b> <code>{esc(trace_id)}</code>",
                    f"<b>Time:</b> {esc(when)}",
                    "",
                    f"<b>Message:</b>\n<pre>{safe_msg}</pre>",
                ]
                if safe_details:
                    text_parts.append(f"\n<b>Details:</b>\n<pre>{safe_details}</pre>")
                text = "\n".join(text_parts)
                # Telegram max message ~4096 chars. Keep a safety margin.
                MAX_LEN = 3900
                if len(text) > MAX_LEN:
                    # Trim details first, then message if still too long
                    if safe_details:
                        head = "\n".join(text_parts[:-1])  # everything before details
                        remaining = (
                            MAX_LEN - len(head) - len("\n<b>Details:</b>\n<pre></pre>")
                        )
                        if remaining < 0:
                            remaining = 0
                        safe_details = safe_details[:remaining]
                        text = head + f"\n<b>Details:</b>\n<pre>{safe_details}</pre>"
                    if len(text) > MAX_LEN:
                        base = "\n".join(text_parts[:6])  # header lines
                        remaining = MAX_LEN - len(base) - len("\n<pre></pre>")
                        if remaining < 0:
                            remaining = 0
                        safe_msg = safe_msg[:remaining]
                        text = base + f"\n<pre>{safe_msg}</pre>"

                payload = {
                    "chat_id": settings.telegram.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                }
                if getattr(settings.telegram, "tg_chat_logs_thread_id", None):
                    payload["message_thread_id"] = (
                        settings.telegram.tg_chat_logs_thread_id
                    )
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                resp = urllib.request.urlopen(
                    req, timeout=6
                )  # nosec - trusted API endpoint
                body = ""
                try:
                    body = resp.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
                if getattr(resp, "status", 200) != 200:
                    sys.stderr.write(
                        f"[telegram_alerts] HTTP {getattr(resp,'status',0)}: {body[:500]}\n"
                    )
                else:
                    # Parse JSON and confirm ok
                    try:
                        data_json = json.loads(body) if body else {"ok": True}
                    except Exception:
                        data_json = {"ok": True}
                    if not data_json.get("ok", True):
                        sys.stderr.write(
                            f"[telegram_alerts] API not ok: {str(data_json)[:500]}\n"
                        )
                        raise urllib.error.HTTPError(
                            url, 200, "Telegram ok=false", hdrs=None, fp=None
                        )
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
                sys.stderr.write(
                    f"[telegram_alerts] HTTPError {e.code}: {body[:500]}\n"
                )
                # Fallback: send minimal plain-text message without HTML
                try:
                    plain = f"APP LOG ALERT\nLevel: {record.levelname}\nLogger: {record.name}\nTrace: {trace_id}\nTime: {when}\n\nMessage: {raw_msg[:1000]}"
                    payload2 = {"chat_id": settings.telegram.chat_id, "text": plain}
                    if getattr(settings.telegram, "tg_chat_logs_thread_id", None):
                        payload2["message_thread_id"] = (
                            settings.telegram.tg_chat_logs_thread_id
                        )
                    data2 = json.dumps(payload2).encode("utf-8")
                    req2 = urllib.request.Request(
                        url,
                        data=data2,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    try:
                        resp2 = urllib.request.urlopen(req2, timeout=4)
                        body2 = resp2.read().decode("utf-8", errors="ignore")
                    except Exception as ee:
                        body2 = str(ee)
                    if getattr(resp2, "status", 200) != 200:
                        try:
                            body2 = body2 or resp2.read().decode(
                                "utf-8", errors="ignore"
                            )
                        except Exception:
                            body2 = "<no body>"
                        sys.stderr.write(
                            f"[telegram_alerts] Fallback HTTP {getattr(resp2,'status',0)}: {body2[:500]}\n"
                        )
                    # If error mentions message_thread_id, retry without thread id
                    if (
                        "message_thread_id" in (body or "").lower()
                        or "message_thread_id" in (body2 or "").lower()
                    ):
                        try:
                            payload3 = {
                                "chat_id": settings.telegram.chat_id,
                                "text": plain,
                            }
                            data3 = json.dumps(payload3).encode("utf-8")
                            req3 = urllib.request.Request(
                                url,
                                data=data3,
                                headers={"Content-Type": "application/json"},
                                method="POST",
                            )
                            urllib.request.urlopen(req3, timeout=4)
                            sys.stderr.write(
                                "[telegram_alerts] Retried without message_thread_id.\n"
                            )
                        except Exception as e3:
                            sys.stderr.write(
                                f"[telegram_alerts] Retry without thread failed: {e3}\n"
                            )
                except Exception as e2:
                    sys.stderr.write(f"[telegram_alerts] Fallback send failed: {e2}\n")
            except Exception as e:
                sys.stderr.write(f"[telegram_alerts] Send failed: {e}\n")
        except Exception:
            # Never raise from logging handler
            pass


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
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "with_trace": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | [%(trace_id)s] | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # Uvicorn access logs are very chatty; keep them concise
            "uvicorn_access": {
                "format": "%(asctime)s | %(levelname)-8s | %(channel)-20s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "with_trace" if level == "DEBUG" else "default",
                "level": level,
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "uvicorn_console": {
                "class": "logging.StreamHandler",
                "formatter": "uvicorn_access",
                "level": (
                    "INFO" if level == "DEBUG" else level
                ),  # Reduce uvicorn access verbosity in DEBUG
                "stream": "ext://sys.stdout",
                "filters": ["channel", "trace"],
            },
            "telegram_alerts": {
                "class": "core.logging_config.TelegramLogHandler",
                "level": "WARNING",
            },
        },
        "loggers": {
            # App-level
            "": {  # root
                "handlers": ["console", "telegram_alerts"],
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
                "handlers": ["console", "telegram_alerts"],
                "level": level,
                "propagate": False,
            },
            "celery.app.trace": {
                "handlers": ["console", "telegram_alerts"],
                "level": level,
                "propagate": False,
            },
            # SQLAlchemy warnings/errors (DB constraint violations, etc.)
            "sqlalchemy": {
                "handlers": ["console", "telegram_alerts"],
                "level": "WARNING",
                "propagate": False,
            },
            # Suppress noisy third-party libraries in non-DEBUG mode
            "agents": {
                "handlers": ["console"],
                "level": level if level == "DEBUG" else "WARNING",
                "propagate": False,
            },
            "openai": {
                "handlers": ["console"],
                "level": level if level == "DEBUG" else "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }

    # Optionally disable telegram alerts via env flag
    if os.getenv("DISABLE_TELEGRAM_LOG_ALERTS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        # Remove telegram handler from root logger
        try:
            config["loggers"][""]["handlers"].remove("telegram_alerts")
        except Exception:
            pass

    dictConfig(config)
    logging.getLogger(__name__).debug("Logging configured with level %s", level)
