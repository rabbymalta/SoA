"""The Order aggregate's event store.

The order has no "current state" column anywhere. Its state is the fold of its
events, and the read model in Section 2 is a projection that trails them. Appending
is guarded by a conditional write on the sequence number, so two concurrent writers
cannot both claim the same position.
"""
import time
from typing import Any

from . import aws, config
from .logging import log


def append(order_id: str, seq: int, event_type: str, payload: dict, correlation_id: str) -> bool:
    """Appends one event at `seq`. False means another writer got there first."""
    written = aws.put(config.TABLES["order_events"], {
        "order_id": order_id,
        "seq": seq,
        "event_type": event_type,
        "payload": payload,
        "correlation_id": correlation_id,
        "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, condition="attribute_not_exists(order_id) AND attribute_not_exists(seq)")
    if written:
        log("info", "event.appended", event_type=event_type, seq=seq)
    else:
        log("warn", "event.append_conflict", event_type=event_type, seq=seq)
    return written


def read(order_id: str) -> list[dict]:
    return aws.query(config.TABLES["order_events"], "order_id = :o", {":o": order_id})


# The fold. Adding a state is adding a line here, and nothing is ever updated in place.
_APPLY: dict[str, str] = {
    "OrderPlaced": "PENDING",
    "StockReserved": "STOCK_RESERVED",
    "StockRejected": "REJECTED",
    "PaymentAuthorised": "PAID",
    "PaymentDeclined": "COMPENSATING",
    "StockReleased": "CANCELLED",
    "OrderConfirmed": "CONFIRMED",
    "OrderCancelled": "CANCELLED",
}

# SQS standard queues do not preserve order, so a fact can be appended after a
# later one. The fold therefore never moves an order backwards, and never moves
# it at all once it has reached a terminal state.
_RANK = {"UNKNOWN": -1, "PENDING": 0, "STOCK_RESERVED": 1, "COMPENSATING": 2, "PAID": 2}
_TERMINAL = {"CONFIRMED", "CANCELLED", "REJECTED"}


def fold(history: list[dict]) -> dict[str, Any]:
    """Rebuilds the order from its events. This is the only definition of 'the order'."""
    state: dict[str, Any] = {"state": "UNKNOWN", "timeline": [], "version": 0}
    for event in history:
        payload = event.get("payload") or {}
        state["version"] = int(event["seq"])
        candidate = _APPLY.get(event["event_type"], state["state"])
        if state["state"] not in _TERMINAL and candidate != state["state"]:
            if candidate in _TERMINAL or _RANK.get(candidate, 0) >= _RANK.get(state["state"], -1):
                state["state"] = candidate
        state["timeline"].append({"seq": int(event["seq"]), "event": event["event_type"],
                                  "at": event.get("occurred_at")})
        if event["event_type"] == "OrderPlaced":
            state.update({
                "order_id": payload.get("order_id"),
                "customer_id": payload.get("customer_id"),
                "total_cents": payload.get("total_cents"),
                "currency": payload.get("currency", "EUR"),
                "lines": payload.get("lines", []),
                "correlation_id": event.get("correlation_id"),
            })
        if event["event_type"] in ("StockRejected", "PaymentDeclined"):
            state["failure_reason"] = payload.get("reason")
        if event["event_type"] == "PaymentAuthorised":
            state["psp_reference"] = payload.get("psp_reference")
    return state
