"""Consumer-driven contract test.

notification-service is the consumer and owns `contracts/order-confirmed.v1.schema.json`.
The producer of OrderConfirmed is the workflow, which builds the detail from its
state-machine Parameters block, so the test expands that block exactly as the
engine does. A field renamed in the workflow fails here, before it is deployed.
"""
import json
import uuid
from pathlib import Path

from app import engine
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "contracts" / "order-confirmed.v1.schema.json").read_text())
DEFINITION = json.loads((ROOT / "contracts" / "place-order.asl.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


def published_detail(**overrides) -> dict:
    """Builds the detail exactly as the ConfirmOrder state does, then adds the two
    envelope fields the bus client stamps on every event."""
    data = {
        "order_id": str(uuid.uuid4()),
        "customer_id": "MT-C-7741",
        "total_cents": 37800,
        "lines": [{"sku": "COFFEE-DLX", "quantity": 1}, {"sku": "KETTLE-TMP", "quantity": 2}],
        "payment": {"status": "AUTHORISED", "psp_reference": "psp_8f2c1a0b9d44"},
    }
    data.update(overrides)
    detail = engine.resolve(DEFINITION["States"]["ConfirmOrder"]["Parameters"], data, None)["Detail"]
    return {**detail, "event_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}


def test_the_published_event_satisfies_the_consumer_contract():
    errors = sorted(VALIDATOR.iter_errors(published_detail()), key=lambda e: e.path)
    assert not errors, [e.message for e in errors]


def test_the_contract_fails_without_a_correlation_id():
    detail = published_detail()
    del detail["correlation_id"]
    assert not VALIDATOR.is_valid(detail)


def test_the_contract_fails_if_the_total_becomes_formatted_text():
    detail = published_detail()
    detail["total_cents"] = "378.00"
    assert not VALIDATOR.is_valid(detail)


def test_the_contract_fails_on_an_order_with_no_lines():
    detail = published_detail(lines=[])
    assert not VALIDATOR.is_valid(detail)
