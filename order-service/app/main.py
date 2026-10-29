"""Order service: the REST edge, the event store and the read model.

The order has no state column. `POST /orders` appends OrderPlaced to the event
store and starts a workflow execution; every later fact arrives as an event and is
appended too. A projector trails the store and maintains a read model, so queries
never replay history and the write side never serves reads.
"""
import uuid

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from maltashop import aws, config, eventstore, worker
from maltashop.logging import log, set_correlation, set_order

app = FastAPI(title="MaltaShop order service", docs_url="/docs")

PRICES = {           # a local replica of catalogue prices, so checkout calls nobody
    "COFFEE-DLX": 24900, "VACUUM-V9": 38900, "KETTLE-TMP": 6450,
    "IRON-STEAM": 8990, "MONITOR-27U": 74900, "SOLD-OUT-PRO": 15900,
}


# --------------------------------------------------------------- the write side

@app.post("/orders")
async def place_order(request: Request, response: Response) -> JSONResponse:
    body = await request.json()
    correlation = request.headers.get("x-correlation-id") or str(uuid.uuid4())
    idempotency_key = request.headers.get("idempotency-key") or str(uuid.uuid4())
    set_correlation(correlation)
    response.headers["x-correlation-id"] = correlation

    customer_id, items = body.get("customer_id"), body.get("items")
    if not customer_id or not isinstance(items, list) or not items:
        return JSONResponse(status_code=400,
                            content={"error": "customer_id and a non-empty items array are required"})

    # The idempotency key is the partition key of its own item, so a retry cannot
    # create a second order even if two requests arrive at the same instant.
    existing = aws.get(config.TABLES["order_view"], {"order_id": f"key#{idempotency_key}"})
    if existing:
        log("info", "order.idempotent_replay", order_id=existing["maps_to"])
        view = aws.get(config.TABLES["order_view"], {"order_id": existing["maps_to"]}) or {}
        return JSONResponse(status_code=200, content={"order_id": existing["maps_to"],
                                                      "state": view.get("state", "PENDING"),
                                                      "replayed": True})

    priced, total = [], 0
    for line in items:
        unit = PRICES.get(line.get("sku"))
        if unit is None:
            return JSONResponse(status_code=422, content={"error": f"unknown sku {line.get('sku')}"})
        quantity = int(line.get("quantity", 0))
        if quantity <= 0:
            return JSONResponse(status_code=422, content={"error": f"invalid quantity for {line['sku']}"})
        total += unit * quantity
        priced.append({"sku": line["sku"], "quantity": quantity, "unit_cents": unit})

    order_id = str(uuid.uuid4())
    set_order(order_id)
    payload = {"order_id": order_id, "customer_id": customer_id, "total_cents": total,
               "currency": "EUR",
               "lines": [{"sku": line["sku"], "quantity": line["quantity"]} for line in priced]}

    if not eventstore.append(order_id, 1, "OrderPlaced", payload, correlation):
        return JSONResponse(status_code=409, content={"error": "order already exists"})
    aws.put(config.TABLES["order_view"], {"order_id": f"key#{idempotency_key}", "maps_to": order_id})
    _project(order_id)

    with httpx.Client(timeout=10) as client:
        execution = client.post(f"{config.WORKFLOW_URL}/executions", json=payload,
                                headers={"x-correlation-id": correlation}).json()
    aws.put(config.TABLES["order_view"], {**(aws.get(config.TABLES["order_view"], {"order_id": order_id}) or {}),
                                          "execution_id": execution.get("execution_id")})

    log("info", "order.accepted", total_cents=total, lines=len(priced),
        execution_id=execution.get("execution_id"))
    response.headers["location"] = f"/orders/{order_id}"
    return JSONResponse(status_code=201, headers={"location": f"/orders/{order_id}",
                                                  "x-correlation-id": correlation},
                        content={"order_id": order_id, "state": "PENDING", "total_cents": total,
                                 "currency": "EUR", "correlation_id": correlation,
                                 "execution_id": execution.get("execution_id"),
                                 "message": "Order received. Stock and payment are being confirmed."})


# ---------------------------------------------------------------- the read side

def _project(order_id: str) -> dict:
    """Folds the event stream and writes the read model. In AWS this runs from a
    DynamoDB stream; here a poller calls it, which is the same shape, slower."""
    history = eventstore.read(order_id)
    if not history:
        return {}
    view = eventstore.fold(history)
    existing = aws.get(config.TABLES["order_view"], {"order_id": order_id}) or {}
    view["order_id"] = order_id
    view["execution_id"] = existing.get("execution_id")
    aws.put(config.TABLES["order_view"], view)
    return view


@app.get("/orders/{order_id}")
def get_order(order_id: str, consistent: bool = False) -> JSONResponse:
    """`?consistent=true` folds the events on the spot instead of reading the
    projection, which is how the eventual consistency in Section 1.3 is made visible."""
    if consistent:
        history = eventstore.read(order_id)
        if not history:
            return JSONResponse(status_code=404, content={"error": "order not found"})
        view = eventstore.fold(history)
        view["order_id"] = order_id
        view["source"] = "event-store (folded on read)"
        return JSONResponse(status_code=200, content=view)
    view = aws.get(config.TABLES["order_view"], {"order_id": order_id})
    if not view:
        return JSONResponse(status_code=404, content={"error": "order not found"})
    view["source"] = "read model (projection)"
    return JSONResponse(status_code=200, content=view)


@app.get("/orders/{order_id}/events")
def get_events(order_id: str) -> list[dict]:
    return [{"seq": int(e["seq"]), "event_type": e["event_type"], "occurred_at": e.get("occurred_at")}
            for e in eventstore.read(order_id)]


@app.get("/health/live")
def live() -> dict:
    return {"status": "alive", "service": config.SERVICE_NAME, "version": config.SERVICE_VERSION}


@app.get("/health/ready")
def ready() -> JSONResponse:
    try:
        aws.dynamodb().describe_table(TableName=config.TABLES["order_events"])
        return JSONResponse(status_code=200, content={"status": "ready", "service": config.SERVICE_NAME})
    except Exception as error:
        return JSONResponse(status_code=503, content={"status": "not-ready", "reason": str(error)})


# ------------------------------------------------- the saga's facts, as events

def _on_event(detail: dict) -> None:
    """Appends a fact the saga produced to the order's stream, then re-projects."""
    order_id = detail.get("order_id")
    event_type = detail.get("__detail_type") or detail.get("event_type")
    if not order_id or not event_type:
        return
    if not worker.claim_once(detail.get("event_id", str(uuid.uuid4()))):
        log("info", "event.duplicate_ignored", detail_type=event_type)
        return
    history = eventstore.read(order_id)
    if not history:
        log("warn", "event.unknown_order", detail_type=event_type)
        return
    seq = max(int(e["seq"]) for e in history) + 1
    eventstore.append(order_id, seq, event_type, detail, detail.get("correlation_id", "none"))
    _project(order_id)


@app.on_event("startup")
def start_consumer() -> None:
    def handle(detail: dict) -> None:
        _on_event(detail)
        return None
    worker.run(config.QUEUES["order"], handle, callback=False)
    log("info", "service.started", port=config.PORT)
