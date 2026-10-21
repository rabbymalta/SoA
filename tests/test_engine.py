"""Unit tests for the states-language engine: paths, parameters and choices.

These are what make the workflow safe to change: the saga is a declaration, so a
mistake in it is caught here rather than in production.
"""
import json
from pathlib import Path

from app import engine

DEFINITION = json.loads((Path(__file__).resolve().parent.parent /
                         "contracts" / "place-order.asl.json").read_text())


def test_a_path_reads_a_nested_value():
    data = {"order_id": "o-1", "stock": {"status": "RESERVED"}}
    assert engine.read_path(data, "$.order_id") == "o-1"
    assert engine.read_path(data, "$.stock.status") == "RESERVED"
    assert engine.read_path(data, "$.stock.missing") is None


def test_a_result_is_written_at_the_result_path():
    data = {"order_id": "o-1"}
    engine.write_path(data, "$.payment", {"status": "DECLINED", "reason": "card_ceiling_exceeded"})
    assert data["payment"]["reason"] == "card_ceiling_exceeded"


def test_parameters_expand_paths_and_the_task_token():
    template = DEFINITION["States"]["ReserveStock"]["Parameters"]
    resolved = engine.resolve(template, {"order_id": "o-1", "lines": [{"sku": "A", "quantity": 2}]}, "tok-9")
    assert resolved["QueueName"] == "maltashop-inventory-tasks"
    assert resolved["MessageBody"]["order_id"] == "o-1"
    assert resolved["MessageBody"]["taskToken"] == "tok-9"
    assert resolved["MessageBody"]["command"] == "ReserveStock"


def test_a_choice_routes_on_the_worker_s_answer():
    stock = DEFINITION["States"]["StockOutcome"]
    assert engine._choose(stock, {"stock": {"status": "RESERVED"}}) == "AuthorisePayment"
    assert engine._choose(stock, {"stock": {"status": "REJECTED"}}) == "RejectOrder"
    payment = DEFINITION["States"]["PaymentOutcome"]
    assert engine._choose(payment, {"payment": {"status": "AUTHORISED"}}) == "ConfirmOrder"
    assert engine._choose(payment, {"payment": {"status": "DECLINED"}}) == "ReleaseStock"


def test_a_declined_payment_is_routed_to_the_compensating_state():
    assert DEFINITION["States"]["ReleaseStock"]["Next"] == "CancelOrder"
    assert DEFINITION["States"]["ReleaseStock"]["Resource"].endswith("waitForTaskToken")


def test_every_task_that_waits_for_a_worker_has_a_timeout():
    for name, state in DEFINITION["States"].items():
        if state.get("Resource", "").endswith("waitForTaskToken"):
            assert "TimeoutSeconds" in state, f"{name} could wait for ever"
