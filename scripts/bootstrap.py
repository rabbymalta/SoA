"""Creates every AWS resource the platform needs, then exits.

In AWS this work is done by the CDK stack in `infra/`; here the same shapes are
created against LocalStack so that `docker compose up` produces a running system.
The script is idempotent, so it is safe on every start.
"""
import json
import sys
import time

from maltashop import aws, config
from maltashop.logging import log

TABLES = [
    (config.TABLES["order_events"], [("order_id", "S", "HASH"), ("seq", "N", "RANGE")]),
    (config.TABLES["order_view"], [("order_id", "S", "HASH")]),
    (config.TABLES["inventory"], [("sku", "S", "HASH")]),
    (config.TABLES["payments"], [("order_id", "S", "HASH")]),
    (config.TABLES["notifications"], [("order_id", "S", "HASH"), ("notification_id", "S", "RANGE")]),
    (config.TABLES["executions"], [("execution_id", "S", "HASH")]),
    ("maltashop-tasks", [("task_token", "S", "HASH")]),
    ("maltashop-processed", [("event_id", "S", "HASH")]),
]

# Each rule is one consumer's subscription. Adding a consumer adds a rule and a
# queue; no producer is touched, which is the property Section 2.2 relies on.
RULES = [
    ("maltashop-order-projection", ["StockReserved", "StockRejected", "PaymentAuthorised",
                                    "PaymentDeclined", "StockReleased", "OrderConfirmed",
                                    "OrderCancelled"], config.QUEUES["order"]),
    ("maltashop-notification-fanout", ["OrderConfirmed", "OrderCancelled"], config.QUEUES["notification"]),
    ("maltashop-inventory-commit", ["OrderConfirmed"], config.QUEUES["inventory"]),
]

STOCK = [
    ("COFFEE-DLX", "Valletta Deluxe bean-to-cup machine", 18, 24900),
    ("VACUUM-V9", "Mdina V9 cordless vacuum", 26, 38900),
    ("KETTLE-TMP", "Marsaxlokk temperature kettle", 140, 6450),
    ("IRON-STEAM", "Zebbug steam generator iron", 61, 8990),
    ("MONITOR-27U", "Naxxar 27\" 4K monitor", 12, 74900),
    ("SOLD-OUT-PRO", "Dingli Pro blender (sold out)", 0, 15900),
]


def wait_for_localstack(attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            aws.dynamodb().list_tables()
            return
        except Exception:
            time.sleep(2)
    raise SystemExit("LocalStack did not become available")


def create_tables() -> None:
    client = aws.dynamodb()
    existing = set(client.list_tables()["TableNames"])
    for name, keys in TABLES:
        if name in existing:
            continue
        client.create_table(
            TableName=name,
            AttributeDefinitions=[{"AttributeName": a, "AttributeType": t} for a, t, _ in keys],
            KeySchema=[{"AttributeName": a, "KeyType": k} for a, _, k in keys],
            BillingMode="PAY_PER_REQUEST")
        client.get_waiter("table_exists").wait(TableName=name)
        log("info", "table.created", table=name)


def create_bus_and_queues() -> None:
    events, sqs = aws.events(), aws.sqs()
    buses = {b["Name"] for b in events.list_event_buses()["EventBuses"]}
    if config.EVENT_BUS not in buses:
        events.create_event_bus(Name=config.EVENT_BUS)
        log("info", "bus.created", bus=config.EVENT_BUS)

    for queue in config.QUEUES.values():
        sqs.create_queue(QueueName=queue, Attributes={"VisibilityTimeout": "30",
                                                      "MessageRetentionPeriod": "1209600"})
    # A dead-letter queue for anything a consumer cannot handle after five attempts.
    sqs.create_queue(QueueName="maltashop-dlq")
    log("info", "queues.created", queues=list(config.QUEUES.values()) + ["maltashop-dlq"])

    for rule, detail_types, queue in RULES:
        events.put_rule(
            Name=rule, EventBusName=config.EVENT_BUS, State="ENABLED",
            EventPattern=json.dumps({"source": ["maltashop.checkout"], "detail-type": detail_types}))
        arn = sqs.get_queue_attributes(QueueUrl=aws.queue_url(queue),
                                       AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
        events.put_targets(Rule=rule, EventBusName=config.EVENT_BUS,
                           Targets=[{"Id": f"{rule}-target", "Arn": arn}])
        log("info", "rule.created", rule=rule, detail_types=detail_types, queue=queue)


def seed_stock() -> None:
    for sku, description, on_hand, unit_cents in STOCK:
        aws.put(config.TABLES["inventory"], {
            "sku": sku, "description": description, "on_hand": on_hand,
            "reserved": 0, "unit_cents": unit_cents})
    log("info", "stock.seeded", skus=len(STOCK))


def main() -> int:
    wait_for_localstack()
    create_tables()
    create_bus_and_queues()
    seed_stock()
    log("info", "bootstrap.complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
