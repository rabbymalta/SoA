"""Unit tests for the fold: the only definition of what an order is.

No DynamoDB, no network, milliseconds to run. These are the base of the pyramid.
"""
from maltashop.eventstore import fold


def event(seq, event_type, payload=None):
    return {"seq": seq, "event_type": event_type, "payload": payload or {},
            "correlation_id": "c-1", "occurred_at": "2026-11-10T09:00:00Z"}


PLACED = event(1, "OrderPlaced", {"order_id": "o-1", "customer_id": "MT-C-7741",
                                  "total_cents": 37800, "currency": "EUR",
                                  "lines": [{"sku": "COFFEE-DLX", "quantity": 1}]})


def test_an_order_is_the_fold_of_its_events():
    state = fold([PLACED, event(2, "StockReserved"), event(3, "PaymentAuthorised"),
                  event(4, "OrderConfirmed")])
    assert state["state"] == "CONFIRMED"
    assert state["version"] == 4
    assert state["total_cents"] == 37800
    assert [step["event"] for step in state["timeline"]] == [
        "OrderPlaced", "StockReserved", "PaymentAuthorised", "OrderConfirmed"]


def test_the_compensating_path_ends_cancelled():
    state = fold([PLACED, event(2, "StockReserved"),
                  event(3, "PaymentDeclined", {"reason": "card_ceiling_exceeded"}),
                  event(4, "StockReleased"), event(5, "OrderCancelled")])
    assert state["state"] == "CANCELLED"
    assert state["failure_reason"] == "card_ceiling_exceeded"


def test_an_out_of_stock_order_never_reaches_payment():
    state = fold([PLACED, event(2, "StockRejected", {"reason": "insufficient_stock:SOLD-OUT-PRO"})])
    assert state["state"] == "REJECTED"
    assert state["failure_reason"] == "insufficient_stock:SOLD-OUT-PRO"


def test_a_terminal_order_is_not_moved_by_a_late_event():
    """SQS does not preserve order, so a fact can arrive after a later one. The fold
    must not walk a confirmed order backwards when that happens."""
    state = fold([PLACED, event(2, "StockReserved"), event(3, "OrderConfirmed"),
                  event(4, "PaymentAuthorised")])
    assert state["state"] == "CONFIRMED"


def test_an_empty_stream_has_no_order():
    assert fold([])["state"] == "UNKNOWN"
