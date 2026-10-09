"""Thin wrappers over the AWS services the design uses.

Only boto3 appears here. Every other module talks to DynamoDB, EventBridge and SQS
through these functions, so moving from LocalStack to AWS is a change of endpoint.
"""
import functools
import json
import uuid
from collections.abc import Iterable
from typing import Any

import boto3
from botocore.config import Config as BotoConfig

from . import config
from .logging import correlation_id, log

_boto = BotoConfig(retries={"max_attempts": 5, "mode": "standard"}, connect_timeout=3, read_timeout=10)


@functools.lru_cache(maxsize=8)
def _client(service: str):
    return boto3.client(service, region_name=config.REGION, endpoint_url=config.ENDPOINT_URL, config=_boto)


@functools.lru_cache(maxsize=16)
def _queue_url_cached(name: str) -> str:
    return sqs().get_queue_url(QueueName=name)["QueueUrl"]


def dynamodb():
    return _client("dynamodb")


def events():
    return _client("events")


def sqs():
    return _client("sqs")


def queue_url(name: str) -> str:
    return _queue_url_cached(name)


# ------------------------------------------------------------------ EventBridge

def publish(detail_type: str, detail: dict, source: str = "maltashop.checkout") -> str:
    """Puts one event on the bus. EventBridge rules decide who receives it, so a new
    consumer is a rule, never a change to this call."""
    event_id = str(uuid.uuid4())
    detail = {**detail, "event_id": event_id, "correlation_id": correlation_id()}
    events().put_events(Entries=[{
        "EventBusName": config.EVENT_BUS,
        "Source": source,
        "DetailType": detail_type,
        "Detail": json.dumps(detail),
    }])
    log("info", "event.published", detail_type=detail_type, event_id=event_id)
    return event_id


# --------------------------------------------------------------------- SQS

def send_task(queue: str, body: dict) -> None:
    sqs().send_message(QueueUrl=queue_url(queue), MessageBody=json.dumps(body))


def receive(queue: str, wait_seconds: int = 10, max_messages: int = 5) -> Iterable[dict]:
    response = sqs().receive_message(
        QueueUrl=queue_url(queue), MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_seconds, VisibilityTimeout=30)
    return response.get("Messages", [])


def delete(queue: str, receipt_handle: str) -> None:
    sqs().delete_message(QueueUrl=queue_url(queue), ReceiptHandle=receipt_handle)


# ---------------------------------------------------------------- DynamoDB

def to_item(value: Any) -> dict:
    """Marshals a Python value into DynamoDB's wire format."""
    if value is None:
        return {"NULL": True}
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, int | float):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, list):
        return {"L": [to_item(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {k: to_item(v) for k, v in value.items()}}
    raise TypeError(f"cannot store {type(value)!r} in DynamoDB")


def from_item(item: Any) -> Any:
    """Unmarshals DynamoDB's wire format back into Python values."""
    if not isinstance(item, dict) or len(item) != 1:
        return item
    kind, value = next(iter(item.items()))
    if kind == "NULL":
        return None
    if kind == "BOOL":
        return value
    if kind == "N":
        number = float(value)
        return int(number) if number.is_integer() else number
    if kind == "S":
        return value
    if kind == "L":
        return [from_item(v) for v in value]
    if kind == "M":
        return {k: from_item(v) for k, v in value.items()}
    return value


def put(table: str, record: dict, condition: str | None = None) -> bool:
    """Writes one item. Returns False when `condition` rejected it, which is how
    optimistic concurrency and idempotency are both enforced."""
    kwargs = {"TableName": table, "Item": {k: to_item(v) for k, v in record.items()}}
    if condition:
        kwargs["ConditionExpression"] = condition
    try:
        dynamodb().put_item(**kwargs)
        return True
    except dynamodb().exceptions.ConditionalCheckFailedException:
        return False


def get(table: str, key: dict) -> dict | None:
    response = dynamodb().get_item(TableName=table, Key={k: to_item(v) for k, v in key.items()})
    item = response.get("Item")
    return {k: from_item(v) for k, v in item.items()} if item else None


def query(table: str, expression: str, values: dict, ascending: bool = True) -> list[dict]:
    response = dynamodb().query(
        TableName=table,
        KeyConditionExpression=expression,
        ExpressionAttributeValues={k: to_item(v) for k, v in values.items()},
        ScanIndexForward=ascending)
    return [{k: from_item(v) for k, v in item.items()} for item in response.get("Items", [])]


def scan(table: str, limit: int = 100) -> list[dict]:
    response = dynamodb().scan(TableName=table, Limit=limit)
    return [{k: from_item(v) for k, v in item.items()} for item in response.get("Items", [])]
