"""Inventory service: a task worker and an event consumer.

It answers two commands from the workflow - reserve and release - and listens for
one event, OrderConfirmed, which turns a reservation into a real deduction. It has
never heard of the Payment service, and it does not know what the workflow will do
with its answer.
"""
from fastapi import FastAPI

from maltashop import aws, config, worker
from maltashop.logging import log

app = FastAPI(title="MaltaShop inventory service", docs_url="/docs")
HOLDS = "maltashop-inventory"        # same table, hold rows keyed by order#<id>


def _hold_key(order_id: str) -> str:
    return f"order#{order_id}"


def reserve(detail: dict) -> dict:
    order_id, lines = detail["order_id"], detail.get("lines", [])
    held = aws.get(config.TABLES["inventory"], {"sku": _hold_key(order_id)})
    if held:                                            # the task was redelivered
        log("info", "stock.reserve_replayed", state=held.get("state"))
        return {"status": "RESERVED" if held.get("state") == "HELD" else "REJECTED",
                "reason": held.get("reason", "")}

    for line in sorted(lines, key=lambda item: item["sku"]):
        item = aws.get(config.TABLES["inventory"], {"sku": line["sku"]})
        if not item:
            return _reject(order_id, lines, f"unknown_sku:{line['sku']}")
        if int(item["on_hand"]) - int(item["reserved"]) < int(line["quantity"]):
            return _reject(order_id, lines, f"insufficient_stock:{line['sku']}")

    for line in lines:
        item = aws.get(config.TABLES["inventory"], {"sku": line["sku"]})
        aws.put(config.TABLES["inventory"], {**item, "reserved": int(item["reserved"]) + int(line["quantity"])})
    aws.put(config.TABLES["inventory"], {"sku": _hold_key(order_id), "state": "HELD", "lines": lines})
    log("info", "stock.reserved", lines=len(lines))
    # The outcome goes two ways: back to the workflow as a task token, and onto the
    # bus as a fact, which is what the order's event stream records.
    aws.publish("StockReserved", {"order_id": order_id})
    return {"status": "RESERVED"}


def _reject(order_id: str, lines: list, reason: str) -> dict:
    aws.put(config.TABLES["inventory"], {"sku": _hold_key(order_id), "state": "REJECTED",
                                         "lines": lines, "reason": reason})
    log("warn", "stock.rejected", reason=reason)
    aws.publish("StockRejected", {"order_id": order_id, "reason": reason})
    return {"status": "REJECTED", "reason": reason}


def release(detail: dict) -> dict:
    """The compensating action. It must be safe to run twice and safe to run when
    nothing was ever held, because the workflow may retry it."""
    order_id = detail["order_id"]
    held = aws.get(config.TABLES["inventory"], {"sku": _hold_key(order_id)})
    if not held or held.get("state") != "HELD":
        log("info", "stock.release_noop", state=(held or {}).get("state", "none"))
        return {"status": "RELEASED"}
    for line in held.get("lines", []):
        item = aws.get(config.TABLES["inventory"], {"sku": line["sku"]})
        aws.put(config.TABLES["inventory"],
                {**item, "reserved": max(int(item["reserved"]) - int(line["quantity"]), 0)})
    aws.put(config.TABLES["inventory"], {**held, "state": "RELEASED"})
    log("info", "stock.released")
    aws.publish("StockReleased", {"order_id": order_id})
    return {"status": "RELEASED"}


def commit(detail: dict) -> None:
    """OrderConfirmed: the hold becomes a deduction."""
    order_id = detail["order_id"]
    held = aws.get(config.TABLES["inventory"], {"sku": _hold_key(order_id)})
    if not held or held.get("state") != "HELD":
        return
    for line in held.get("lines", []):
        item = aws.get(config.TABLES["inventory"], {"sku": line["sku"]})
        aws.put(config.TABLES["inventory"], {
            **item,
            "on_hand": int(item["on_hand"]) - int(line["quantity"]),
            "reserved": max(int(item["reserved"]) - int(line["quantity"]), 0)})
    aws.put(config.TABLES["inventory"], {**held, "state": "COMMITTED"})
    log("info", "stock.committed")


def handle(detail: dict) -> dict | None:
    command = detail.get("command")
    if command == "ReserveStock":
        return reserve(detail)
    if command == "ReleaseStock":
        return release(detail)
    if detail.get("__detail_type") == "OrderConfirmed":
        commit(detail)
    return None


@app.on_event("startup")
def start() -> None:
    worker.run(config.QUEUES["inventory"], handle)
    log("info", "service.started", port=config.PORT)


@app.get("/stock")
def stock() -> list[dict]:
    rows = [r for r in aws.scan(config.TABLES["inventory"], limit=100) if not r["sku"].startswith("order#")]
    return sorted([{"sku": r["sku"], "description": r.get("description", ""),
                    "on_hand": int(r["on_hand"]), "reserved": int(r["reserved"]),
                    "available": int(r["on_hand"]) - int(r["reserved"])} for r in rows],
                  key=lambda r: r["sku"])


@app.get("/health/live")
def live() -> dict:
    return {"status": "alive", "service": config.SERVICE_NAME, "version": config.SERVICE_VERSION}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ready", "service": config.SERVICE_NAME}
