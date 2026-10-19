"""Workflow service: the saga's orchestrator, and nothing else.

It owns the sequence and the compensation, it knows no business rules, and it
holds no business data. In AWS this container disappears entirely and the state
machine runs on Step Functions; the HTTP API below is the local stand-in for the
StartExecution and SendTaskSuccess calls.
"""
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from maltashop import config
from maltashop.logging import log, set_correlation

from . import engine

app = FastAPI(title="MaltaShop workflow service", docs_url="/docs")
DEFINITION = engine.load(config.STATE_MACHINE)


@app.on_event("startup")
def start_sweeper() -> None:
    def loop() -> None:
        while True:
            try:
                engine.sweep(DEFINITION)
            except Exception as error:          # a sweeper that dies is worse than one that logs
                log("error", "workflow.sweep_failed", error=str(error))
            time.sleep(5)
    threading.Thread(target=loop, daemon=True).start()
    log("info", "service.started", states=len(DEFINITION["States"]))


@app.get("/health/live")
def live() -> dict:
    return {"status": "alive", "service": config.SERVICE_NAME, "version": config.SERVICE_VERSION}


@app.get("/health/ready")
def ready() -> dict:
    return {"status": "ready", "service": config.SERVICE_NAME, "states": len(DEFINITION["States"])}


@app.post("/executions")
async def start_execution(request: Request) -> JSONResponse:
    """StartExecution. The input document is the saga's whole working memory."""
    body = await request.json()
    correlation = request.headers.get("x-correlation-id", "none")
    set_correlation(correlation)
    execution = engine.start(DEFINITION, body, correlation)
    return JSONResponse(status_code=202, content={
        "execution_id": execution["execution_id"],
        "status": execution["status"],
        "state": execution["state"],
    })


@app.post("/tasks/{token}/success")
async def task_success(token: str, request: Request) -> JSONResponse:
    """SendTaskSuccess. A worker returns the opaque token it was handed, with its result."""
    result = await request.json()
    execution = engine.succeed(DEFINITION, token, result)
    if execution is None:
        return JSONResponse(status_code=409, content={"error": "unknown, expired or already-used task token"})
    return JSONResponse(status_code=200, content={
        "execution_id": execution["execution_id"],
        "status": execution["status"],
        "state": execution["state"],
    })


@app.get("/executions/{execution_id}")
def get_execution(execution_id: str) -> JSONResponse:
    execution = engine.get(execution_id)
    if not execution:
        return JSONResponse(status_code=404, content={"error": "no such execution"})
    return JSONResponse(status_code=200, content={
        "execution_id": execution["execution_id"],
        "status": execution["status"],
        "state": execution["state"],
        "path": [step["state"] for step in execution.get("history", [])],
        "data": execution["data"],
    })


@app.get("/executions")
def list_executions() -> list[dict]:
    from maltashop import aws
    return [{"execution_id": e["execution_id"], "status": e["status"], "state": e["state"],
             "path": [s["state"] for s in e.get("history", [])]}
            for e in aws.scan(config.TABLES["executions"], limit=50)]
