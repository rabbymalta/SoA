#!/usr/bin/env python3
"""Draws the report's figures.

One bold element per figure and everything else quiet: the spine in Figure 1, the
alias split in Figure 2, the error budget drawn to scale in Figure 3, the sequence
rail in Figure 4. Figure 5 is an inventory and stays deliberately plain.
"""
from svgkit import (OUT, svg, text, lines, rule, vrule, box, node, arrow, path, spine, seq,
                    bar, store, INK, RULE, QUIET, COMMIT, UNDO, WASH, WHITE)

W = 880


def write(name, width, height, body):
    (OUT / f"{name}.svg").write_text(svg(width, height, body))
    print(f"  {name}.svg  {width}x{height}")


# ------------------------------------------------------------------ Figure 1
def architecture():
    h = 600
    p = []

    # clients: named, not boxed. They are outside the system.
    for i, (name, who) in enumerate((("Web storefront", "customers"), ("Mobile app", "customers"),
                                     ("Partner API", "30 retailers"))):
        x = 92 + i * 200
        p.append(text(x, 26, name, size=13, weight="600"))
        p.append(text(x, 42, who, size=10.5, colour=QUIET))
        p.append(arrow(x, 52, x, 76, "rule"))

    # the edge: one thing, three jobs
    p.append(node(24, 80, 560, 46, "", (), stroke=INK))
    p.append(text(44, 101, "API Gateway", size=13, anchor="start", weight="600"))
    p.append(text(44, 117, "throttling and request validation", size=10.5, anchor="start", colour=QUIET))
    p.append(vrule(246, 80, 126))
    p.append(text(266, 101, "Lambda authorizer", size=13, anchor="start", weight="600"))
    p.append(text(266, 117, "customer tokens, one API key per retailer", size=10.5, anchor="start", colour=QUIET))

    # the write path: a chain, because it is one
    p.append(text(24, 168, "The one synchronous step", size=12.5, anchor="start", weight="600", colour=COMMIT))
    p.append(node(24, 180, 170, 76, "place-order", ("appends OrderPlaced,", "answers 201"), stroke=COMMIT))
    p.append(store(36, 232, "order-events", colour=COMMIT))
    p.append(arrow(194, 218, 230, 218, "commit"))
    p.append(node(230, 180, 160, 76, "workflow", ("the saga, declared;", "holds the sequence"), stroke=COMMIT))
    p.append(arrow(390, 204, 426, 204, "commit"))
    p.append(node(426, 180, 148, 76, "inventory", ("holds stock",), stroke=INK))
    p.append(store(438, 232, "inventory"))
    p.append(arrow(390, 232, 426, 232, "commit", dashed=True))
    p.append(node(590, 180, 148, 76, "payment", ("asks the provider",), stroke=INK))
    p.append(store(602, 232, "payments"))
    p.append(path([(574, 204), (582, 204), (582, 218), (590, 218)], "commit"))
    p.append(text(500, 172, "task token out, answer back", size=10, colour=QUIET))

    p.append(node(754, 180, 102, 76, "catalogue", ("products,", "prices"), stroke=INK, fill=WASH))
    p.append(path([(584, 103), (805, 103), (805, 176)], "rule"))

    # the spine: the one bold object in this figure. A dot is a producer writing
    # to it; a consumer reads through a rule, so it gets an arrow and no dot.
    p.append(spine(330, 24, 856, "maltashop-bus", "one rule per consumer"))
    for x, colour in ((140, "commit"), (310, "commit"), (500, "ink"), (664, "ink")):
        p.append(arrow(x, 258, x, 326, colour))
        p.append(f'<circle cx="{x}" cy="330" r="3.2" fill="{INK}"/>')

    # consumers: below the line, each one a rule and a queue
    consumers = [("projector", ("folds the stream into", "the order read model"), INK),
                 ("notification", ("e-mail and SMS;", "nothing waits for it"), INK),
                 ("recommendation", ("reads the same stream,", "never the till"), INK),
                 ("partner feed", ("one queue per retailer,", "added without a release"), INK)]
    for i, (name, rows, stroke) in enumerate(consumers):
        x = 24 + i * 212
        p.append(arrow(x + 98, 334, x + 98, 392, "ink"))
        p.append(node(x, 396, 196, 72, name, rows, stroke=stroke))

    p.append(rule(24, 512, 856))
    p.append(lines(440, 534, [
        "Nothing above is a server. Every box is a function invoked on demand, a managed service or a table,",
        "so capacity during a sale is not a decision anybody makes.",
    ], size=11.5, colour=QUIET, italic=True, gap=18))
    p.append(lines(440, 576, [
        "Solid line, a call. Dashed line, a message. Green, the path that commits.",
    ], size=10.5, colour=QUIET, gap=15))
    write("architecture", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 2
def pipeline():
    h = 470
    p = []

    stages = [("verify", ("ruff, bandit", "unit and contract tests")),
              ("build once", ("one bundle", "its digest recorded")),
              ("integration", ("compose up", "both failure paths")),
              ("deploy", ("the recorded bundle,", "never a rebuild"))]
    p.append(text(24, 30, "git push", size=13, anchor="start", weight="600"))
    p.append(arrow(24, 40, 24, 58, "rule"))
    for i, (name, rows) in enumerate(stages):
        x = 24 + i * 212
        p.append(node(x, 58, 188, 74, name, rows, stroke=INK))
        if i:
            p.append(arrow(x - 20, 95, x - 4, 95, "ink"))
    p.append(text(24, 158, "No approval gate anywhere. What replaces it is drawn below.",
                  size=11.5, anchor="start", colour=QUIET, italic=True))

    # the bold moment: the alias split, drawn to scale
    p.append(rule(24, 180, 856))
    p.append(text(24, 206, "The release: ten per cent of invocations, for five minutes",
                  size=13.5, anchor="start", weight="600"))

    p.append(text(24, 240, "live alias", size=11, anchor="start", colour=QUIET))
    p.append(f'<rect x="24" y="250" width="396" height="34" fill="{WASH}" stroke="{RULE}" stroke-width="0.9"/>')
    p.append(f'<rect x="24" y="250" width="356" height="34" fill="{WHITE}" stroke="{INK}" stroke-width="1.1"/>')
    p.append(text(202, 272, "version N, taking 90 per cent", size=12.5))
    p.append(f'<rect x="380" y="250" width="40" height="34" fill="{COMMIT}"/>')
    p.append(text(400, 272, "N+1", size=10.5, colour=WHITE, weight="600"))
    p.append(text(400, 300, "10%", size=10.5, colour=COMMIT, weight="600"))

    p.append(arrow(424, 267, 452, 267, "ink"))
    p.append(node(456, 232, 182, 70, "three alarms", ("checkout 5xx rate", "checkout p99",
                                                      "failed executions"), stroke=INK))
    p.append(arrow(638, 250, 666, 250, "commit"))
    p.append(node(670, 228, 186, 40, "promote to 100%", (), stroke=COMMIT))
    p.append(arrow(638, 284, 666, 284, "undo"))
    p.append(node(670, 274, 186, 40, "reset the alias", (), stroke=UNDO))
    p.append(text(856, 330, "any one alarm reverses the shift in seconds",
                  size=10.5, anchor="end", colour=UNDO))

    p.append(rule(24, 364, 856))
    p.append(lines(24, 390, [
        "Trunk-based development: a branch that outlives a day is a review comment.",
        "Lead time 23 days to under 2 hours. Deployment frequency 17 a year to 20 a week.",
    ], size=11.5, anchor="start", colour=QUIET, gap=20))
    p.append(text(24, 442, "The bundle built in stage two is the only artefact any later stage deploys.",
                  size=11.5, anchor="start", colour=INK, italic=True))
    write("pipeline", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 3
def observability():
    h = 452
    p = []

    for i, name in enumerate(("place-order", "workflow", "inventory", "payment", "notification")):
        x = 70 + i * 172
        p.append(text(x, 30, name, size=12.5, weight="600"))
        p.append(arrow(x, 40, 440, 92, "rule"))
    p.append(text(24, 76, "every handler, instrumented with OpenTelemetry",
                  size=10.5, anchor="start", colour=QUIET, italic=True))

    p.append(node(252, 96, 376, 44, "Collector", (), stroke=INK))
    p.append(text(440, 128, "redacts anything personal before it leaves the account",
                  size=10.5, colour=QUIET))
    p.append(arrow(440, 140, 440, 164, "ink"))
    p.append(node(252, 168, 376, 50, "Honeycomb", (), stroke=INK))
    p.append(text(440, 204, "one wide event per span: order, customer, sku, workflow state",
                  size=10.5, colour=QUIET))

    p.append(node(672, 96, 184, 122, "CloudWatch", ("infrastructure metrics,", "and the three alarms",
                                                    "the release reads"), stroke=INK, fill=WASH))

    # the bold moment: a week of error budget, drawn to scale
    p.append(rule(24, 254, 856))
    p.append(text(24, 282, "One week of checkout, and the budget inside it",
                  size=13.5, anchor="start", weight="600"))
    p.append(text(24, 306, "99.95% answering in 750 ms or less, measured over seven days",
                  size=11, anchor="start", colour=QUIET))

    p.append(bar(24, 318, 520, 26, 0.0005 * 40, UNDO))
    p.append(text(24, 362, "the whole week", size=10.5, anchor="start", colour=QUIET))
    p.append(text(568, 330, "5 min 2 s of budget", size=12, anchor="start", colour=UNDO, weight="600"))
    p.append(text(568, 348, "drawn forty times its true width, or it would be invisible",
                  size=10, anchor="start", colour=QUIET, italic=True))

    p.append(rule(24, 388, 856))
    p.append(lines(24, 412, [
        "Burning it 14.4 times too fast for five minutes pages the on-call engineer.",
        "Six times too fast for an hour reaches Slack, to be answered the same working day.",
    ], size=11.5, anchor="start", colour=INK, gap=20))
    write("observability", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 4
def saga():
    h = 572
    p = []

    p.append(text(24, 28, "What the file declares", size=13.5, anchor="start", weight="600"))

    states = [("ReserveStock", "waits for a worker", 24),
              ("StockOutcome", "reads the answer", 196),
              ("AuthorisePayment", "waits for a worker", 352),
              ("PaymentOutcome", "reads the answer", 544)]
    for name, role, x in states:
        w = 150 if "Outcome" not in name else 136
        p.append(node(x, 46, w, 56, name, (role,), stroke=INK))
    for x1, x2 in ((174, 192), (332, 348), (502, 540)):
        p.append(arrow(x1, 74, x2, 74, "ink"))

    p.append(node(700, 46, 156, 56, "ConfirmOrder", ("publishes, and ends",), stroke=COMMIT))
    p.append(arrow(680, 74, 696, 74, "commit"))

    p.append(node(352, 136, 150, 56, "ReleaseStock", ("hands the hold back",), stroke=UNDO))
    p.append(path([(612, 102), (612, 118), (427, 118), (427, 132)], "undo"))
    p.append(text(520, 113, "declined", size=10.5, colour=UNDO))
    p.append(node(352, 212, 150, 44, "CancelOrder", (), stroke=UNDO))
    p.append(arrow(427, 192, 427, 208, "undo"))

    p.append(node(24, 136, 150, 56, "RejectOrder", ("nothing was held",), stroke=UNDO))
    p.append(path([(264, 102), (264, 118), (99, 118), (99, 132)], "undo"))
    p.append(text(182, 113, "no stock", size=10.5, colour=UNDO))

    p.append(rule(24, 292, 856))

    # the bold moment: the stream that this declaration actually produced
    p.append(text(24, 320, "How a worker is asked", size=12.5, anchor="start", weight="600"))
    p.append(lines(24, 344, [
        "Two Task states wait on a worker. The workflow hands out an",
        "opaque token and does nothing until the worker returns it, so",
        "Inventory has never heard of Payment and neither knows what",
        "follows its answer.",
        "",
        "Every waiting state carries a timeout and a catch, so a worker",
        "that never answers ends the saga rather than leaving it open.",
    ], size=11.5, anchor="start", colour=INK, gap=19))

    p.append(vrule(528, 300, 500, colour=RULE))

    p.append(text(560, 320, "What one order's stream recorded", size=12.5,
                  anchor="start", weight="600"))
    p.append(vrule(576, 338, 492, colour=RULE))
    for i, (number, label, detail, colour) in enumerate((
            (1, "OrderPlaced", "written with the order, in one transaction", INK),
            (2, "StockReserved", "the hold, published by Inventory", INK),
            (3, "PaymentAuthorised", "the provider's reference", INK),
            (4, "OrderConfirmed", "the workflow's last state", COMMIT))):
        p.append(seq(576, 350 + i * 38, number, label, detail, colour))

    p.append(rule(24, 522, 856))
    p.append(text(24, 548, "Nothing is rolled back. ReleaseStock is an ordinary operation, safe to run "
                           "twice and safe when nothing was held.",
                  size=11, anchor="start", colour=QUIET, italic=True))
    write("saga", W, h, "\n".join(p))


# ------------------------------------------------------------------ Figure 5
def prototype():
    h = 400
    p = []

    p.append(text(24, 28, "docker compose up, and seven containers", size=13.5,
                  anchor="start", weight="600"))

    p.append(node(24, 48, 832, 92, "localstack", (), stroke=INK, fill=WASH))
    p.append(text(440, 92, "DynamoDB, EventBridge, SQS and IAM in one container",
                  size=12, colour=INK))
    p.append(text(440, 112, "eight tables, one bus, three rules, five queues",
                  size=10.5, colour=QUIET))
    p.append(text(440, 130, "the only difference from AWS is one environment variable",
                  size=10.5, colour=QUIET, italic=True))

    for i, (name, port) in enumerate((("order", "9280"), ("workflow", "9284"), ("inventory", "9281"),
                                      ("payment", "9282"), ("notification", "9283"))):
        x = 24 + i * 172
        stroke = COMMIT if name in ("order", "workflow") else INK
        p.append(node(x, 176, 152, 50, name, (), stroke=stroke, size=12.5))
        p.append(text(x + 76, 212, f"port {port}", size=10, colour=QUIET))
        p.append(arrow(x + 76, 174, x + 76, 144, "rule", both=True))

    p.append(rule(24, 258, 856))
    p.append(text(24, 284, "What it shows", size=12.5, anchor="start", weight="600", colour=COMMIT))
    p.append(lines(24, 306, [
        "checkout answers in about 150 ms, and keeps answering",
        "while the notification handler is stopped",
        "the order is the fold of its events, and the read model agrees",
        "a declined card runs the compensating state",
    ], size=11, anchor="start", colour=INK, gap=17))

    p.append(vrule(440, 272, 384, colour=RULE))
    p.append(text(464, 284, "What it does not", size=12.5, anchor="start", weight="600", colour=UNDO))
    p.append(lines(464, 306, [
        "Step Functions itself: the same file is interpreted locally,",
        "so timeout behaviour is approximated",
        "no gateway, no authorizer, no IAM boundaries",
        "no load test; 150 ms is one request on an idle laptop",
    ], size=11, anchor="start", colour=INK, gap=17))
    write("prototype", W, h, "\n".join(p))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    pipeline()
    observability()
    saga()
    prototype()
