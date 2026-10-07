"""Structured JSON logging with a correlation ID carried on a context variable."""
import contextvars
import json
import sys
import time

from . import config

_correlation: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="none")
_order: contextvars.ContextVar[str] = contextvars.ContextVar("order_id", default="")

_LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def set_correlation(value: str) -> None:
    _correlation.set(value or "none")


def set_order(value: str) -> None:
    _order.set(value or "")


def correlation_id() -> str:
    return _correlation.get()


def log(level: str, event: str, **fields) -> None:
    """One JSON object per line on stdout; CloudWatch and Honeycomb read it from there."""
    if _LEVELS.get(level, 20) < _LEVELS.get(config.LOG_LEVEL, 20):
        return
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}Z",
        "level": level,
        "service": config.SERVICE_NAME,
        "version": config.SERVICE_VERSION,
        "environment": config.ENVIRONMENT,
        "correlation_id": _correlation.get(),
        "event": event,
    }
    if _order.get():
        record["order_id"] = _order.get()
    record.update(fields)
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()
