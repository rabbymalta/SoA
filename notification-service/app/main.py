"""Notification service: an EventBridge rule, a queue and a handler.

It subscribes to outcomes. Nothing in checkout waits for it, and adding it to the
platform required a rule and a queue - not one line of change in any producer.
"""
import uuid

from fastapi import FastAPI

from maltashop import aws, config, worker
from maltashop.logging import correlation_id, log

app = FastAPI(title="MaltaShop notification service", docs_url="/docs")

TEMPLATES = {
    "OrderConfirmed": ("order-confirmed", "MaltaShop order {short} confirmed",
                       "Thank you. We have taken EUR {amount} for {count} item(s)."),
    "OrderCancelled": ("order-cancelled", "MaltaShop order {short} could not be completed",
                       "We are sorry: your order was not completed ({reason}). You have not been charged."),
}


def handle(detail: dict) -> None:
    detail_type = detail.get("__detail_type", "")
    template = TEMPLATES.get(detail_type)
    if not template:
        return
    if not worker.claim_once(detail.get("event_id", str(uuid.uuid4()))):
        log("info", "event.duplicate_ignored", detail_type=detail_type)
        return
    name, subject, body = template
    order_id = detail["order_id"]
    aws.put(config.TABLES["notifications"], {
        "order_id": order_id,
        "notification_id": str(uuid.uuid4()),
        "channel": "email",
        "template": name,
        "subject": subject.format(short=order_id[:8]),
        "body": body.format(amount=f"{int(detail.get('total_cents', 0)) / 100:.2f}",
                            count=len(detail.get("lines", [])), reason=detail.get("reason", "")),
        "status": "SENT",
        "correlation_id": correlation_id(),
    })
    log("info", "notification.sent", template=name, channel="email")


@app.on_event("startup")
def start() -> None:
    worker.run(config.QUEUES["notification"], handle, callback=False)
    log("info", "service.started", port=config.PORT)


@app.get("/notifications")
def notifications(order_id: str | None = None) -> list[dict]:
    rows = aws.scan(config.TABLES["notifications"], limit=100)
    if order_id:
        rows = [r for r in rows if r["order_id"] == order_id]
    return rows


@app.get("/health/live")
def live() -> dict:
    return {"status": "alive", "service": config.SERVICE_NAME, "version": config.SERVICE_VERSION}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ready", "service": config.SERVICE_NAME}
