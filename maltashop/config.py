"""Configuration, read from the environment at import time (12-factor III).

Nothing here reads a file. The same bundle runs on a laptop against LocalStack and
in AWS against the real services; only the environment differs.
"""
import os

SERVICE_NAME = os.environ.get("SERVICE_NAME", "unnamed-service")
SERVICE_VERSION = os.environ.get("SERVICE_VERSION", "0.0.0")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "local")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "info").lower()
PORT = int(os.environ.get("PORT", "8080"))

REGION = os.environ.get("AWS_REGION", "eu-south-1")
ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL") or None   # unset in AWS
EVENT_BUS = os.environ.get("EVENT_BUS", "maltashop-bus")
WORKFLOW_URL = os.environ.get("WORKFLOW_URL", "http://workflow-service:8084")
CARD_CEILING_CENTS = int(os.environ.get("CARD_CEILING_EUR", "600")) * 100
STATE_MACHINE = os.environ.get("STATE_MACHINE", "/app/contracts/place-order.asl.json")

# One table per service: no service may read another's table, and in AWS each
# function's execution role grants access to its own table only.
TABLES = {
    "order_events": "maltashop-order-events",
    "order_view": "maltashop-order-view",
    "inventory": "maltashop-inventory",
    "payments": "maltashop-payments",
    "notifications": "maltashop-notifications",
    "executions": "maltashop-executions",
}

QUEUES = {
    "inventory": "maltashop-inventory-tasks",
    "payment": "maltashop-payment-tasks",
    "notification": "maltashop-notification-events",
    "order": "maltashop-order-events-queue",
}
