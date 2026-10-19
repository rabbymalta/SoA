"""A minimal Amazon States Language engine.

AWS Step Functions is a managed service, so it cannot run inside Compose. This
module interprets the *same* `contracts/place-order.asl.json` that is deployed to
Step Functions in AWS, supporting exactly the subset the saga uses: Task states
with the `sqs:sendMessage.waitForTaskToken` and `events:putEvents` integrations,
Choice states, Catch on `States.Timeout`, and ResultPath.

The task-token protocol is the important part and is reproduced faithfully: the
engine hands a worker an opaque token, the worker does its own local transaction,
and the workflow only advances when the worker returns that token. No worker ever
knows which state it is in, or what comes next.
"""
import json
import time
import uuid
from typing import Any

from maltashop import aws, config
from maltashop.logging import log, set_correlation, set_order

TASKS_TABLE = "maltashop-tasks"


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


# ------------------------------------------------------------- JSONPath subset

def read_path(data: dict, path: str) -> Any:
    if path == "$":
        return data
    cursor: Any = data
    for part in path.removeprefix("$.").split("."):
        if cursor is None:
            return None
        cursor = cursor.get(part) if isinstance(cursor, dict) else None
    return cursor


def write_path(data: dict, path: str, value: Any) -> None:
    if path in ("$", None):
        data.update(value if isinstance(value, dict) else {"result": value})
        return
    parts = path.removeprefix("$.").split(".")
    cursor = data
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value


def resolve(template: Any, data: dict, token: str | None) -> Any:
    """Expands a Parameters block: keys ending in `.$` are paths, everything else literal."""
    if isinstance(template, dict):
        out: dict[str, Any] = {}
        for key, value in template.items():
            if key.endswith(".$"):
                name = key[:-2]
                out[name] = token if value == "$$.Task.Token" else read_path(data, value)
            else:
                out[key] = resolve(value, data, token)
        return out
    if isinstance(template, list):
        return [resolve(item, data, token) for item in template]
    return template


# ------------------------------------------------------------------ execution

def _save(execution: dict) -> None:
    aws.put(config.TABLES["executions"], execution)


def _load(execution_id: str) -> dict | None:
    return aws.get(config.TABLES["executions"], {"execution_id": execution_id})


def start(definition: dict, data: dict, correlation_id: str) -> dict:
    execution = {
        "execution_id": str(uuid.uuid4()),
        "status": "RUNNING",
        "state": definition["StartAt"],
        "data": data,
        "history": [],
        "correlation_id": correlation_id,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _save(execution)
    log("info", "workflow.started", execution_id=execution["execution_id"], start_at=execution["state"])
    return advance(definition, execution)


def advance(definition: dict, execution: dict) -> dict:
    """Runs states until the workflow blocks on a task token or reaches an end state."""
    set_correlation(execution.get("correlation_id", "none"))
    set_order(execution["data"].get("order_id", ""))
    guard = 0
    while execution["status"] == "RUNNING":
        guard += 1
        if guard > 50:                      # a malformed definition must not spin forever
            execution["status"] = "FAILED"
            execution["error"] = "States.Runtime: too many transitions"
            break
        name = execution["state"]
        state = definition["States"][name]
        execution["history"].append({"state": name, "at": time.strftime("%H:%M:%S", time.gmtime())})

        if state["Type"] == "Choice":
            execution["state"] = _choose(state, execution["data"])
            continue

        if state["Type"] != "Task":
            execution["status"] = "FAILED"
            execution["error"] = f"States.Runtime: unsupported state type {state['Type']}"
            break

        resource = state["Resource"]
        if resource.endswith("sqs:sendMessage.waitForTaskToken"):
            token = str(uuid.uuid4())
            params = resolve(state["Parameters"], execution["data"], token)
            params["MessageBody"]["correlation_id"] = execution.get("correlation_id", "none")
            aws.put(TASKS_TABLE, {
                "task_token": token,
                "execution_id": execution["execution_id"],
                "state": name,
                "timeout_seconds": int(state.get("TimeoutSeconds", 60)),
                "issued_at": int(time.time()),
                "status": "PENDING",
            })
            aws.send_task(params["QueueName"], params["MessageBody"])
            execution["status"] = "WAITING"
            log("info", "workflow.task_dispatched", state=name,
                queue=params["QueueName"], task_token=token[:8])
            break

        if resource.endswith("events:putEvents"):
            params = resolve(state["Parameters"], execution["data"], None)
            aws.publish(params["DetailType"], params["Detail"])
            log("info", "workflow.event_emitted", state=name, detail_type=params["DetailType"])
            if state.get("End"):
                execution["status"] = "SUCCEEDED"
                break
            execution["state"] = state["Next"]
            continue

        execution["status"] = "FAILED"
        execution["error"] = f"States.Runtime: unsupported resource {resource}"
        break

    _save(execution)
    return execution


def _choose(state: dict, data: dict) -> str:
    for choice in state.get("Choices", []):
        if "StringEquals" in choice and read_path(data, choice["Variable"]) == choice["StringEquals"]:
            return choice["Next"]
    return state["Default"]


def succeed(definition: dict, token: str, result: dict) -> dict | None:
    """The SendTaskSuccess call. The worker returns the token it was given, and the
    workflow writes the worker's output into the document at ResultPath."""
    task = aws.get(TASKS_TABLE, {"task_token": token})
    if not task or task.get("status") != "PENDING":
        log("warn", "workflow.token_rejected", task_token=token[:8])
        return None
    aws.put(TASKS_TABLE, {**task, "status": "DONE"})
    execution = _load(task["execution_id"])
    if not execution or execution["status"] != "WAITING":
        return None

    state = definition["States"][task["state"]]
    write_path(execution["data"], state.get("ResultPath", "$"), result)
    execution["state"] = state["Next"]
    execution["status"] = "RUNNING"
    log("info", "workflow.task_returned", state=task["state"], result=result.get("status"))
    return advance(definition, execution)


def sweep(definition: dict) -> int:
    """Fails tasks that waited longer than their TimeoutSeconds and routes them to the
    state's Catch, so a worker that never answers cannot leave a saga open for ever."""
    timed_out = 0
    now = int(time.time())
    for task in aws.scan(TASKS_TABLE, limit=200):
        if task.get("status") != "PENDING" or now - int(task["issued_at"]) <= int(task["timeout_seconds"]):
            continue
        aws.put(TASKS_TABLE, {**task, "status": "TIMED_OUT"})
        execution = _load(task["execution_id"])
        if not execution or execution["status"] != "WAITING":
            continue
        state = definition["States"][task["state"]]
        catch = next((c for c in state.get("Catch", []) if "States.Timeout" in c["ErrorEquals"]), None)
        set_correlation(execution.get("correlation_id", "none"))
        log("warn", "workflow.task_timed_out", state=task["state"], caught=bool(catch))
        if not catch:
            execution["status"] = "FAILED"
            execution["error"] = "States.Timeout"
            _save(execution)
            continue
        write_path(execution["data"], state.get("ResultPath", "$"),
                   {"status": "TIMEOUT", "reason": "worker_did_not_respond"})
        execution["state"] = catch["Next"]
        execution["status"] = "RUNNING"
        advance(definition, execution)
        timed_out += 1
    return timed_out


def get(execution_id: str) -> dict | None:
    return _load(execution_id)
