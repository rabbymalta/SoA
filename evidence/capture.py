#!/usr/bin/env python3
"""Runs the demonstration behind Sections 3 and 6.3 and saves the evidence.

    python3 evidence/capture.py

Every screenshot renders the real output of the command printed above it, and the
same text is kept in evidence/transcripts/. Needs Docker, curl, jq and Playwright.
"""
import html
import json
import subprocess
import time
import uuid
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
TRANSCRIPTS = ROOT / "evidence" / "transcripts"
SHOTS = ROOT / "evidence" / "screenshots"
ORDER, INVENTORY, PAYMENT, NOTIFY, WORKFLOW = (
    "http://localhost:9280", "http://localhost:9281", "http://localhost:9282",
    "http://localhost:9283", "http://localhost:9284")
BASKET = ('{"customer_id":"MT-C-7741","items":[{"sku":"COFFEE-DLX","quantity":1},'
          '{"sku":"KETTLE-TMP","quantity":2}]}')
BIG = '{"customer_id":"MT-C-7741","items":[{"sku":"MONITOR-27U","quantity":1}]}'
DESCRIBE = "docker compose exec -T order-service python -m scripts.describe_platform"

# An indigo terminal, so this submission's figures are visibly its own.
TERMINAL = """<!doctype html><html><head><meta charset="utf-8"><style>
 body {{ margin:0; padding:20px; background:#ffffff; }}
 .window {{ width:{width}px; border-radius:8px; overflow:hidden; background:#1b1733;
            border:1px solid #cfc9e6; box-shadow:0 2px 8px rgba(40,30,80,.20); }}
 .bar {{ height:31px; background:#2a2350; display:flex; align-items:center; padding:0 14px; }}
 .dot {{ width:10px; height:10px; border-radius:50%; margin-right:8px; }}
 .title {{ color:#b9b1dd; font:12.5px/1 -apple-system, Helvetica, sans-serif; margin-left:12px; }}
 pre {{ margin:0; padding:15px 18px 18px; color:#e9e5f7; font:13.5px/1.5 Menlo, monospace;
        white-space:pre-wrap; word-break:break-all; }}
 .cmd {{ color:#9f8bff; }} .hl {{ color:#ffd166; font-weight:bold; }} .ok {{ color:#6ee7a8; }}
</style></head><body><div class="window"><div class="bar">
 <span class="dot" style="background:#ff5f7e"></span><span class="dot" style="background:#ffc14d"></span>
 <span class="dot" style="background:#4ade80"></span><span class="title">{title}</span></div>
 <pre>{body}</pre></div></body></html>"""


def sh(command, check=True):
    result = subprocess.run(["bash", "-c", command], cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"command failed: {command}\n{result.stdout}{result.stderr}")
    return (result.stdout + result.stderr).rstrip("\n")


class Terminal:
    def __init__(self, browser):
        self.browser = browser

    def capture(self, name, title, commands, highlight=None, width=1020):
        lines = []
        for command in commands:
            lines.append(f"$ {command}")
            output = sh(command)
            if output:
                lines.append(output)
            lines.append("")
        text = "\n".join(lines).rstrip("\n")
        (TRANSCRIPTS / f"{name}.txt").write_text(text + "\n", encoding="utf-8")
        body = "\n".join(
            f'<span class="cmd">{html.escape(row)}</span>' if row.startswith("$ ")
            else f'<span class="ok">{html.escape(row)}</span>' if row.strip().startswith("PASS")
            else html.escape(row) for row in text.splitlines())
        for mark in ([highlight] if isinstance(highlight, str) else (highlight or [])):
            body = body.replace(html.escape(mark), f'<span class="hl">{html.escape(mark)}</span>')
        page = self.browser.new_page(device_scale_factor=2, viewport={"width": width + 44, "height": 400})
        page.set_content(TERMINAL.format(width=width, title=html.escape(title), body=body))
        page.locator(".window").screenshot(path=str(SHOTS / f"{name}.png"))
        page.close()
        print(f"  saved {name}")
        return text


def wait_state(order_id, state, tries=70):
    for _ in range(tries):
        if sh(f"curl -sS {ORDER}/orders/{order_id} | jq -r .state") == state:
            return
        time.sleep(0.5)
    raise SystemExit(f"{order_id} never reached {state}")


def main():
    TRANSCRIPTS.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    print("starting a fresh platform ...")
    sh("docker compose down -v --remove-orphans", check=False)
    sh("docker compose up -d --build --wait")
    time.sleep(4)

    correlation = str(uuid.uuid4())
    key = f"k-{correlation[:8]}"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        term = Terminal(browser)

        term.capture("01_compose_up", "docker compose up: the whole cloud, locally",
                     ["docker compose ps --format 'table {{.Service}}\\t{{.Status}}\\t{{.Ports}}' "
                      "| cut -c1-118"], width=1160)

        term.capture("03_order_request", "POST /orders: the one synchronous step in checkout", [
            f"curl -sS -D /tmp/h.txt -o /tmp/b.json -X POST {ORDER}/orders "
            f"-H 'content-type: application/json' -H 'x-correlation-id: {correlation}' "
            f"-H 'idempotency-key: {key}' -d '{BASKET}'; "
            "grep -Ei '^HTTP|^location|^x-correlation' /tmp/h.txt; jq . /tmp/b.json"],
            highlight=correlation, width=1060)
        placed = json.loads(sh("cat /tmp/b.json"))
        order_id, execution_id = placed["order_id"], placed["execution_id"]
        wait_state(order_id, "CONFIRMED")

        term.capture("04_event_stream", "the order is the fold of its events, and the read model trails them", [
            f"curl -sS {ORDER}/orders/{order_id}/events | jq -c '.[]'",
            f"curl -sS '{ORDER}/orders/{order_id}' | jq '{{state, version, source}}'",
            f"curl -sS '{ORDER}/orders/{order_id}?consistent=true' | jq '{{state, version, source}}'"],
            highlight=order_id, width=1060)

        term.capture("05_workflow_execution", "the declared workflow, and the path this order took", [
            f"curl -sS {WORKFLOW}/executions/{execution_id} "
            "| jq '{status, state, path, stock: .data.stock, payment: .data.payment}'"],
            highlight=execution_id)

        term.capture("06_event_consumed", "notification-service: the OrderConfirmed event, consumed", [
            f"curl -sS '{NOTIFY}/notifications?order_id={order_id}' "
            "| jq '.[] | {template, subject, body, status, correlation_id}'"],
            highlight=[correlation, order_id])

        term.capture("02_aws_resources", "a table per service, a rule per consumer, a queue per subscriber",
                     [f"{DESCRIBE} 2>/dev/null | head -30"], width=1020)

        term.capture("07_correlation_logs", "one correlation ID across five handlers", [
            f"docker compose logs --no-log-prefix | grep {correlation} "
            "| jq -r '[.timestamp[11:23], .service, .event] | @tsv' | sort | column -t -s $'\\t'"],
            highlight=correlation)

        before = sh(f"curl -sS {INVENTORY}/stock | jq -r '.[]|select(.sku==\"MONITOR-27U\")|.available'")
        cid2 = str(uuid.uuid4())
        declined = json.loads(sh(f"curl -sS -X POST {ORDER}/orders -H 'content-type: application/json' "
                                 f"-H 'x-correlation-id: {cid2}' -H 'idempotency-key: dec-{cid2[:8]}' "
                                 f"-d '{BIG}'"))
        wait_state(declined["order_id"], "CANCELLED")
        term.capture("08_compensation", "payment declined: the workflow runs its compensating state", [
            f"echo 'available before the order: {before}'",
            f"curl -sS {WORKFLOW}/executions/{declined['execution_id']} | jq '{{status, path}}'",
            f"curl -sS {ORDER}/orders/{declined['order_id']}/events | jq -r '[.[].event_type] | join(\" -> \")'",
            f"curl -sS {INVENTORY}/stock | jq -r '.[]|select(.sku==\"MONITOR-27U\")"
            "|\"available after compensation: \\(.available)\"'"],
            highlight=declined["order_id"], width=1060)

        print("fault isolation ...")
        cid3 = str(uuid.uuid4())
        out = term.capture("09_fault_isolation", "Notification is down: checkout is unaffected", [
            "docker compose stop notification-service 2>&1 | tail -1",
            f"curl -sS -o /dev/null -w 'checkout answered HTTP %{{http_code}} in %{{time_total}}s\\n' "
            f"-X POST {ORDER}/orders -H 'content-type: application/json' "
            f"-H 'x-correlation-id: {cid3}' -H 'idempotency-key: out-{cid3[:8]}' -d '{BASKET}'",
            f"sleep 6; {DESCRIBE} queues 2>/dev/null | tail -6"], width=1060)
        assert "HTTP 201" in out, out

        term.capture("10_recovery", "Notification restarts and drains its queue", [
            "docker compose start notification-service 2>&1 | tail -1",
            "until curl -fsS http://localhost:9283/health/ready >/dev/null 2>&1; do sleep 1; done; "
            "for _ in $(seq 1 60); do "
            "  n=$(curl -sS http://localhost:9283/notifications | jq length); "
            "  [ \"$n\" -ge 3 ] && break; sleep 2; done; "
            f"{DESCRIBE} queues 2>/dev/null | tail -6",
            f"curl -sS {NOTIFY}/notifications | jq -r '.[] | [.template, .subject] | @tsv' "
            "| head -4 | column -t -s $'\\t'"], width=1060)

        term.capture("11_pipeline_run", "the pipeline's verify, build and integration phases",
                     ["./scripts/run_pipeline.sh"], width=1040)
        browser.close()

    (ROOT / "evidence" / "demo.json").write_text(json.dumps(
        {"order_id": order_id, "execution_id": execution_id, "correlation_id": correlation,
         "cancelled_order_id": declined["order_id"],
         "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=2) + "\n")
    print("done")


if __name__ == "__main__":
    main()
