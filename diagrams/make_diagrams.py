#!/usr/bin/env python3
"""Draws every figure in the report as an SVG in diagrams/src/."""
from svgkit import (OUT, svg, text, text_lines, rect, box, arrow, polyline, line, cylinder,
                    INK, GREY, LIGHT, WHITE, ACCENT, AMBER, AMBER_FILL, BLUE, BLUE_FILL,
                    GREEN, GREEN_FILL)

W = 880


def write(name, width, height, body):
    (OUT / f"{name}.svg").write_text(svg(width, height, body))
    print(f"  {name}.svg  {width}x{height}")


def rule(y, x1=24, x2=856, colour=GREY):
    return line(x1, y, x2, y, colour=colour, width=0.8)


def label(x, y, content, size=11, colour=GREY, anchor="start"):
    return text(x, y, content.upper(), size=size, anchor=anchor, colour=colour, bold=True)


# ------------------------------------------------------------------ Figure 1
def architecture():
    h = 620
    p = [rect(0, 0, W, h, WHITE, WHITE, 0)]

    p.append(label(24, 26, "clients"))
    for i, (name, sub) in enumerate((("Web storefront", "browser"), ("Mobile app", "iOS / Android"),
                                     ("30 partner retailers", "server to server"))):
        x = 24 + i * 282
        p.append(box(x, 36, 264, 44, name, [sub], fill=WHITE, title_size=13.5, size=11.5))
    p.append(rule(96))

    p.append(label(24, 120, "edge — authenticate once, then never again"))
    p.append(rect(24, 130, 832, 50, LIGHT, INK, 1.0))
    p.append(text(180, 152, "API Gateway", size=14, bold=True))
    p.append(text(180, 169, "TLS · throttling · request validation", size=11, colour=GREY))
    p.append(line(336, 130, 336, 180, colour=GREY, width=0.8))
    p.append(text(496, 152, "Lambda authorizer", size=14, bold=True))
    p.append(text(496, 169, "customer JWT · one API key and usage plan per retailer", size=11, colour=GREY))
    p.append(line(656, 130, 656, 180, colour=GREY, width=0.8))
    p.append(text(756, 152, "WAF", size=14, bold=True))
    p.append(text(756, 169, "rate and bot rules", size=11, colour=GREY))
    for x in (160, 440, 740):
        p.append(arrow(x, 80, x, 128, "grey", width=1.0))

    # write side
    p.append(label(224, 212, "write side — one synchronous step"))
    p.append(rect(24, 222, 300, 96, WHITE, ACCENT, 1.6))
    p.append(text(174, 244, "place-order handler", size=14, bold=True, colour=ACCENT))
    p.append(text_lines(174, 263, ["appends OrderPlaced to the stream,",
                                   "starts the workflow, answers 201"], size=11.5, gap=15))
    p.append(cylinder(96, 288, colour=ACCENT))
    p.append(text(192, 304, "order-events  (append only)", size=11.5, anchor="start"))
    p.append(arrow(174, 180, 174, 220, "accent"))

    # the workflow
    p.append(rect(348, 222, 212, 96, AMBER_FILL, AMBER, 1.6))
    p.append(text(454, 244, "Step Functions", size=14, bold=True, colour=AMBER))
    p.append(text_lines(454, 263, ["the place-order saga,", "declared in states language;",
                                   "owns the compensation"], size=11.5, gap=15))
    p.append(arrow(324, 262, 346, 262, "amber"))

    # workers
    for i, (name, store) in enumerate((("Inventory", "inventory"), ("Payment", "payments"))):
        x = 584 + i * 140
        p.append(rect(x, 222, 128, 96, WHITE, INK, 1.0))
        p.append(text(x + 64, 244, name, size=13.5, bold=True))
        p.append(text(x + 64, 261, "task worker", size=10.5, italic=True, colour=GREY))
        p.append(cylinder(x + 10, 274))
        p.append(text(x + 70, 290, store, size=11))
        p.append(text(x + 64, 310, "token in, token out", size=10, italic=True, colour=GREY))
    p.append(arrow(560, 250, 582, 250, "amber", both=True))
    p.append(polyline([(560, 290), (572, 290), (572, 338), (788, 338), (788, 320)], "amber", width=1.2))
    p.append(arrow(788, 338, 788, 320, "amber"))

    # the bus
    p.append(rule(360))
    p.append(label(190, 382, "integration — one bus, one rule per consumer"))
    p.append(rect(24, 392, 832, 48, BLUE_FILL, BLUE, 1.6))
    p.append(text(440, 414, "Amazon EventBridge — maltashop-bus", size=14.5, bold=True, colour=BLUE))
    p.append(text(440, 431, "OrderPlaced · StockReserved · StockRejected · PaymentAuthorised · "
                            "PaymentDeclined · OrderConfirmed · OrderCancelled",
                  size=10.5, colour=GREY))
    p.append(arrow(454, 318, 454, 390, "blue"))
    p.append(polyline([(648, 318), (648, 360), (300, 360), (300, 390)], "blue", width=1.2))

    # read side and consumers
    p.append(label(190, 470, "read side and subscribers — each one a rule and a queue"))
    for i, (name, rows, stroke, fill) in enumerate((
            ("Projector", ["folds the stream into", "the order read model"], INK, WHITE),
            ("Notification", ["e-mail and SMS;", "nothing waits for it"], INK, WHITE),
            ("Recommendation", ["Python model; reads the", "same stream, never the till"], GREEN, GREEN_FILL),
            ("Partner feed", ["one queue per retailer,", "added without a release"], INK, LIGHT))):
        x = 24 + i * 212
        p.append(rect(x, 482, 196, 78, fill, stroke, 1.0))
        p.append(text(x + 98, 503, name, size=13, bold=True, colour=stroke))
        p.append(text_lines(x + 98, 522, rows, size=11, gap=14))
        p.append(arrow(x + 98, 440, x + 98, 480, "blue", width=1.0))

    p.append(rule(578))
    p.append(text(440, 597, "Nothing above is a server: every box is a Lambda function, a managed service "
                            "or a DynamoDB table, and the", size=11, italic=True, colour=GREY))
    p.append(text(440, 605, "platform scales each of them on its own. Plain arrow = synchronous · "
                            "double arrow = task token · line from the bus = a rule.",
                  size=11, italic=True, colour=GREY))
    write("architecture", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 2
def pipeline():
    h = 478
    p = [rect(0, 0, W, h, WHITE, WHITE, 0)]
    p.append(label(24, 26, "codepipeline — source to production, no human in the path"))

    phases = [("source", ["commit on main", "CodeCommit mirror"]),
              ("verify", ["ruff · bandit", "unit + contract tests", "states language parsed"]),
              ("build once", ["one bundle", "SHA-256 recorded", "nothing rebuilt later"]),
              ("integration", ["compose up --wait", "both failure paths"]),
              ("deploy", ["CloudFormation", "change set applied"])]
    for i, (name, rows) in enumerate(phases):
        x = 24 + i * 170
        stroke = ACCENT if name == "verify" else INK
        p.append(rect(x, 42, 152, 84, WHITE, stroke, 1.0))
        p.append(text(x + 76, 63, name, size=13, bold=True, colour=stroke))
        p.append(text_lines(x + 76, 82, rows, size=10.5, gap=14))
        if i:
            p.append(arrow(x - 18, 84, x - 2, 84, "grey", width=1.0))

    p.append(text(440, 150, "the bundle built in phase three is the only artefact any later phase deploys",
                  size=11.5, italic=True, colour=ACCENT))

    p.append(rule(168))
    p.append(label(24, 192, "release — a canary on the live alias, watched by alarms"))

    p.append(rect(24, 204, 832, 150, LIGHT, INK, 1.0))
    # alias weighting
    p.append(rect(48, 228, 180, 54, WHITE, INK, 1.0))
    p.append(text(138, 249, "version N", size=12.5, bold=True))
    p.append(text(138, 266, "90% of invocations", size=10.5, colour=GREY))
    p.append(rect(48, 292, 180, 46, WHITE, ACCENT, 1.4))
    p.append(text(138, 311, "version N+1", size=12.5, bold=True, colour=ACCENT))
    p.append(text(138, 328, "10%, for five minutes", size=10.5, colour=GREY))
    p.append(text(138, 220, "live alias", size=11, italic=True, colour=GREY))

    p.append(arrow(232, 262, 268, 262, "grey", width=1.0))
    p.append(arrow(232, 314, 268, 314, "accent", width=1.0))

    p.append(rect(272, 228, 232, 110, WHITE, INK, 1.0))
    p.append(text(388, 250, "three CloudWatch alarms", size=12.5, bold=True))
    p.append(text_lines(388, 269, ["checkout 5xx rate", "checkout p99 latency",
                                   "failed workflow executions"], size=11, gap=16))
    p.append(text(388, 326, "any one fires → reverse", size=10.5, italic=True, colour=ACCENT))

    p.append(arrow(508, 262, 544, 262, "grey", width=1.0))
    p.append(rect(548, 228, 136, 48, GREEN_FILL, GREEN, 1.2))
    p.append(text(616, 250, "promote", size=12.5, bold=True, colour=GREEN))
    p.append(text(616, 266, "100% to N+1", size=10.5, colour=GREY))

    p.append(arrow(508, 314, 544, 314, "accent", width=1.0))
    p.append(rect(548, 290, 136, 48, "#fdf1e3", ACCENT, 1.2))
    p.append(text(616, 312, "roll back", size=12.5, bold=True, colour=ACCENT))
    p.append(text(616, 328, "alias to N, seconds", size=10.5, colour=GREY))

    p.append(rect(700, 228, 136, 110, WHITE, INK, 1.0))
    p.append(text(768, 250, "hooks", size=12.5, bold=True))
    p.append(text_lines(768, 269, ["pre-traffic: a synthetic", "order on N+1",
                                   "post-traffic: the saga", "completed"], size=10, gap=14))

    p.append(rule(372))
    p.append(text(440, 396, "Continuous deployment: no approval gate anywhere, because the alarms are a "
                            "better judge than a person at 18:00 on a Friday.", size=11.5, italic=True,
                  colour=GREY))
    p.append(text(440, 418, "Trunk-based development; a branch that lives longer than a day is a "
                            "review comment.", size=11.5, italic=True, colour=GREY))
    p.append(text(440, 446, "Deployment frequency 17/year → 20/week   ·   lead time 23 days → under 2 hours",
                  size=12, bold=True, colour=INK))
    write("pipeline", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 3
def observability():
    h = 452
    p = [rect(0, 0, W, h, WHITE, WHITE, 0)]
    p.append(label(24, 26, "instrumentation — wide events, not narrow metrics"))

    for i, name in enumerate(("place-order", "workflow", "inventory", "payment", "notification")):
        x = 24 + i * 170
        p.append(rect(x, 38, 152, 48, WHITE, INK, 1.0))
        p.append(text(x + 76, 58, name, size=12.5, bold=True))
        p.append(text(x + 76, 75, "OpenTelemetry SDK", size=10, colour=GREY))
        p.append(arrow(x + 76, 86, 440, 122, "grey", width=1.0))

    p.append(rect(200, 124, 480, 46, LIGHT, INK, 1.0))
    p.append(text(440, 145, "OpenTelemetry Collector", size=13.5, bold=True))
    p.append(text(440, 162, "redacts names, addresses and anything card-shaped before it leaves the account",
                  size=10.5, colour=GREY))

    p.append(rect(200, 188, 480, 54, AMBER_FILL, AMBER, 1.6))
    p.append(text(440, 210, "Honeycomb", size=14, bold=True, colour=AMBER))
    p.append(text(440, 228, "one wide event per span: correlation_id, order_id, customer_id, sku, "
                            "workflow_state, cold_start", size=10.5, colour=GREY))
    p.append(arrow(440, 170, 440, 186, "grey", width=1.0))

    p.append(rect(700, 124, 156, 118, WHITE, GREY, 1.0, dashed=True))
    p.append(text(778, 146, "CloudWatch", size=12.5, bold=True, colour=GREY))
    p.append(text_lines(778, 165, ["infrastructure metrics", "and the three alarms",
                                   "the canary reads", "(Figure 2)"], size=10, gap=14))

    p.append(rule(262))
    p.append(label(24, 286, "objective and alerts"))

    p.append(rect(24, 298, 404, 130, WHITE, ACCENT, 1.2))
    p.append(text(226, 320, "SLO: checkout", size=13.5, bold=True, colour=ACCENT))
    p.append(text_lines(226, 339, ["99.95% of POST /orders answer 2xx in ≤ 750 ms,",
                                   "measured over a rolling 7 days",
                                   "error budget: 5 min 2 s a week"], size=11, gap=16))
    p.append(line(40, 392, 412, 392, colour=ACCENT, width=0.8, dashed=True))
    p.append(text_lines(226, 408, ["burn 14.4× over 5 min → page the on-call engineer",
                                   "burn 6× over 1 h → Slack, same working day"], size=10.5, gap=15))

    p.append(rect(452, 298, 404, 130, WHITE, INK, 1.0))
    p.append(text(654, 320, "the March incident, on this design", size=13.5, bold=True))
    p.append(text_lines(654, 339, ["1  the e-mail handler leaks; its concurrency climbs",
                                   "2  checkout is untouched — a different function",
                                   "3  one query groups errors by function and version",
                                   "4  the unsent messages are still on the queue",
                                   "5  fifty minutes of lost sales becomes a ticket"],
                        size=10.5, gap=15))
    write("observability", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 4
def saga():
    h = 560
    p = [rect(0, 0, W, h, WHITE, WHITE, 0)]
    p.append(text(440, 26, "The saga is a declaration. This diagram and contracts/place-order.asl.json "
                           "are the same thing.", size=12, italic=True, colour=GREY))

    def state(x, y, w, hh, name, rows, kind="task"):
        stroke = {"task": INK, "choice": BLUE, "end": GREEN, "fail": ACCENT}[kind]
        fill = {"task": WHITE, "choice": BLUE_FILL, "end": GREEN_FILL, "fail": "#fdf1e3"}[kind]
        out = [rect(x, y, w, hh, fill, stroke, 1.4 if kind != "task" else 1.0),
               text(x + w / 2, y + 21, name, size=12.5, bold=True, colour=stroke)]
        out.append(text_lines(x + w / 2, y + 39, rows, size=10.5, gap=14))
        return "\n".join(out)

    p.append(label(24, 56, "the declared states"))
    p.append(state(24, 68, 180, 66, "ReserveStock", ["sqs:sendMessage", ".waitForTaskToken"]))
    p.append(state(236, 68, 136, 66, "StockOutcome", ["Choice on", "$.stock.status"], "choice"))
    p.append(state(404, 68, 180, 66, "AuthorisePayment", ["sqs:sendMessage", ".waitForTaskToken"]))
    p.append(state(616, 68, 136, 66, "PaymentOutcome", ["Choice on", "$.payment.status"], "choice"))
    for x1, x2 in ((204, 234), (372, 402), (584, 614)):
        p.append(arrow(x1, 101, x2, 101, "ink", width=1.2))

    p.append(state(676, 176, 180, 62, "ConfirmOrder", ["events:putEvents", "End"], "end"))
    p.append(polyline([(684, 101), (780, 101), (780, 174)], "ink", width=1.2))
    p.append(text(800, 128, "AUTHORISED", size=10, colour=GREEN, anchor="middle"))

    p.append(state(404, 176, 180, 62, "ReleaseStock", ["the compensating state", "waitForTaskToken"], "fail"))
    p.append(polyline([(684, 134), (684, 155), (494, 155), (494, 174)], "accent", width=1.2))
    p.append(text(560, 150, "DECLINED", size=10, colour=ACCENT))
    p.append(state(404, 262, 180, 56, "CancelOrder", ["events:putEvents · End"], "fail"))
    p.append(arrow(494, 238, 494, 260, "accent", width=1.2))

    p.append(state(136, 176, 180, 62, "RejectOrder", ["events:putEvents", "End"], "fail"))
    p.append(polyline([(304, 134), (304, 155), (226, 155), (226, 174)], "accent", width=1.2))
    p.append(text(272, 150, "REJECTED", size=10, colour=ACCENT))

    p.append(rule(342))
    p.append(label(24, 366, "the task-token protocol, which is what lets a container do the work"))
    p.append(rect(24, 378, 404, 110, WHITE, INK, 1.0))
    p.append(text_lines(226, 400, ["1  the state sends a message carrying an opaque token",
                                   "2  the worker does its own local transaction",
                                   "3  the worker calls SendTaskSuccess with that token",
                                   "4  the workflow writes the output at ResultPath",
                                   "5  the Choice reads it and picks the next state"],
                        size=11, gap=16))
    p.append(rect(452, 378, 404, 110, WHITE, ACCENT, 1.2))
    p.append(text(654, 400, "no worker knows the sequence", size=13, bold=True, colour=ACCENT))
    p.append(text_lines(654, 419, ["Inventory has never heard of Payment. Neither knows",
                                   "what happens after it answers. The order of the steps",
                                   "is in one file, reviewed as one change, and visible as",
                                   "one execution in the console."], size=11, gap=16))

    p.append(text(440, 516, "Every waiting state carries TimeoutSeconds and a Catch, so a worker that never "
                            "answers ends the saga rather than", size=11, italic=True, colour=GREY))
    p.append(text(440, 534, "leaving it open. Nothing is rolled back: ReleaseStock is an ordinary, "
                            "idempotent operation.", size=11, italic=True, colour=GREY))
    write("saga", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 5
def prototype():
    h = 430
    p = [rect(0, 0, W, h, WHITE, WHITE, 0)]
    p.append(label(24, 26, "docker compose up --build -d --wait   ·   seven containers"))

    p.append(rect(24, 40, 832, 120, LIGHT, BLUE, 1.4, dashed=True))
    p.append(text(440, 62, "localstack  —  DynamoDB · EventBridge · SQS · IAM", size=14,
                  bold=True, colour=BLUE))
    p.append(text(440, 80, "the whole cloud in one container; the only difference from AWS is "
                           "AWS_ENDPOINT_URL", size=11, colour=GREY))
    for i, (name, detail) in enumerate((("8 tables", "one per service"), ("1 bus", "maltashop-bus"),
                                        ("3 rules", "one per consumer"), ("5 queues", "plus a dead-letter"))):
        x = 60 + i * 196
        p.append(rect(x, 96, 168, 48, WHITE, INK, 1.0))
        p.append(text(x + 84, 116, name, size=12.5, bold=True))
        p.append(text(x + 84, 133, detail, size=10.5, colour=GREY))

    p.append(label(24, 192, "five handler containers, one image"))
    for i, (name, port) in enumerate((("order", ":9280"), ("workflow", ":9284"), ("inventory", ":9281"),
                                      ("payment", ":9282"), ("notification", ":9283"))):
        x = 24 + i * 170
        stroke = ACCENT if name in ("order", "workflow") else INK
        p.append(rect(x, 204, 152, 56, WHITE, stroke, 1.0))
        p.append(text(x + 76, 226, name, size=12.5, bold=True, colour=stroke))
        p.append(text(x + 76, 243, f"{port}  ·  Python 3.12", size=10.5, colour=GREY))
        p.append(arrow(x + 76, 202, x + 76, 162, "grey", both=True, width=1.0))

    p.append(rule(282))
    p.append(rect(24, 300, 404, 108, WHITE, GREEN, 1.2))
    p.append(text(226, 322, "what the prototype proves", size=13, bold=True, colour=GREEN))
    p.append(text_lines(226, 341, ["checkout answers in ~150 ms and keeps answering",
                                   "while the notification handler is stopped",
                                   "the order is the fold of its events, and the read",
                                   "model agrees with it",
                                   "a declined card runs the compensating state"], size=10.5, gap=14))

    p.append(rect(452, 300, 404, 108, WHITE, ACCENT, 1.2))
    p.append(text(654, 322, "what it does not prove", size=13, bold=True, colour=ACCENT))
    p.append(text_lines(654, 341, ["Step Functions itself: the same ASL file is",
                                   "interpreted locally, so timeout and heartbeat",
                                   "behaviour is approximated",
                                   "no API Gateway, no authorizer, no IAM boundaries",
                                   "no load test: 150 ms is one request on a laptop"],
                        size=10.5, gap=14))
    write("prototype", W, h, "\n".join(p))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    pipeline()
    observability()
    saga()
    prototype()
