"""The SQS worker loop every task handler shares.

In AWS this loop does not exist: Lambda's event source mapping delivers the batch
and the platform handles retries, visibility and the dead-letter queue. The loop
below reproduces that contract locally so the handler code is identical in both.
"""
import json
import threading
import time
from collections.abc import Callable

import httpx

from . import aws, config
from .logging import log, set_correlation, set_order

CallbackResult = dict


def _post_task_success(token: str, result: CallbackResult) -> None:
    """SendTaskSuccess: hands the token back to the workflow with this worker's output."""
    with httpx.Client(timeout=10) as client:
        response = client.post(f"{config.WORKFLOW_URL}/tasks/{token}/success", json=result)
        if response.status_code != 200:
            log("warn", "task.callback_rejected", status=response.status_code)


def run(queue: str, handle: Callable[[dict], CallbackResult | None], *, callback: bool = True) -> None:
    """Polls `queue`, runs `handle`, and returns the task token when one is present."""
    def loop() -> None:
        while True:
            try:
                for message in aws.receive(queue):
                    body = json.loads(message["Body"])
                    # EventBridge wraps the event; a direct task message does not.
                    payload = body.get("detail", body)
                    if "detail-type" in body and isinstance(payload, dict):
                        payload = {**payload, "__detail_type": body["detail-type"]}
                    set_correlation(payload.get("correlation_id", "none"))
                    set_order(payload.get("order_id", ""))
                    try:
                        result = handle(payload)
                        if callback and result is not None and payload.get("taskToken"):
                            _post_task_success(payload["taskToken"], result)
                        aws.delete(queue, message["ReceiptHandle"])
                    except Exception as error:
                        # Leave the message on the queue: SQS redelivers it, and after
                        # five attempts the redrive policy moves it to the dead-letter queue.
                        log("error", "task.failed", queue=queue, error=str(error))
            except Exception as error:
                log("warn", "worker.poll_failed", queue=queue, error=str(error))
                time.sleep(2)
    threading.Thread(target=loop, daemon=True).start()
    log("info", "worker.started", queue=queue)


def claim_once(event_id: str) -> bool:
    """Idempotent consumption, per consumer.

    SQS is at-least-once, so every handler must be safe to run twice. The claim is
    keyed by consumer *and* event, because the same event is delivered to several
    independent consumers and each must be allowed to process it exactly once.
    """
    return aws.put("maltashop-processed",
                   {"event_id": f"{config.SERVICE_NAME}#{event_id}", "seen_at": int(time.time())},
                   condition="attribute_not_exists(event_id)")
