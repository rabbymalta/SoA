"""Payment service: the only component that speaks to the card provider.

It stores the provider's reference and never a card number, so the rest of the
platform stays outside the PCI DSS boundary. The write is conditional on the order
id, which makes a redelivered task a no-op rather than a second charge.
"""
import uuid

from fastapi import FastAPI

from maltashop import aws, config, worker
from maltashop.logging import log

app = FastAPI(title="MaltaShop payment service", docs_url="/docs")


def call_provider(amount_cents: int) -> tuple[str, str]:
    """Stands in for the provider's API. Above the card ceiling it declines, which
    is what makes the saga's compensating path easy to demonstrate."""
    if amount_cents > config.CARD_CEILING_CENTS:
        return "", "card_ceiling_exceeded"
    return f"psp_{uuid.uuid4().hex[:12]}", ""


def authorise(detail: dict) -> dict:
    order_id = detail["order_id"]
    amount = int(detail["amount_cents"])

    existing = aws.get(config.TABLES["payments"], {"order_id": order_id})
    if existing:                                        # the task was redelivered
        log("info", "payment.already_decided", state=existing["state"])
        return {"status": existing["state"], "psp_reference": existing.get("psp_reference", ""),
                "reason": existing.get("decline_reason", "")}

    reference, decline = call_provider(amount)
    state = "DECLINED" if decline else "AUTHORISED"
    aws.put(config.TABLES["payments"], {
        "order_id": order_id, "customer_id": detail.get("customer_id", ""),
        "amount_cents": amount, "currency": "EUR", "state": state,
        "psp_reference": reference, "decline_reason": decline},
        condition="attribute_not_exists(order_id)")

    if decline:
        log("warn", "payment.declined", amount_cents=amount, reason=decline)
        aws.publish("PaymentDeclined", {"order_id": order_id, "reason": decline})
        return {"status": "DECLINED", "reason": decline}
    log("info", "payment.authorised", amount_cents=amount)
    aws.publish("PaymentAuthorised", {"order_id": order_id, "psp_reference": reference})
    return {"status": "AUTHORISED", "psp_reference": reference}


def handle(detail: dict) -> dict | None:
    return authorise(detail) if detail.get("command") == "AuthorisePayment" else None


@app.on_event("startup")
def start() -> None:
    worker.run(config.QUEUES["payment"], handle)
    log("info", "service.started", port=config.PORT, ceiling_cents=config.CARD_CEILING_CENTS)


@app.get("/payments")
def payments(order_id: str | None = None) -> list[dict]:
    if order_id:
        item = aws.get(config.TABLES["payments"], {"order_id": order_id})
        return [item] if item else []
    return aws.scan(config.TABLES["payments"], limit=50)


@app.get("/health/live")
def live() -> dict:
    return {"status": "alive", "service": config.SERVICE_NAME, "version": config.SERVICE_VERSION}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ready", "service": config.SERVICE_NAME}
