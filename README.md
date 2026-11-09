# MaltaShop event-core prototype

A running slice of the serverless MaltaShop platform described in the Unit 5
report: the **place-an-order** flow, built as an **event-sourced** aggregate
coordinated by a **declared workflow**, over **EventBridge** and **SQS**.

Three things make it different from an ordinary microservices prototype:

1. **The order has no state column.** It is the fold of its event stream, and the
   thing you query is a *projection* that trails those events.
2. **The saga is a declaration, not code.** `contracts/place-order.asl.json` is
   Amazon States Language. It is deployed unchanged to AWS Step Functions; the
   prototype's engine interprets the same file.
3. **Workers answer with a task token.** A worker is handed an opaque token, does
   its own local transaction, and hands the token back. No worker knows which step
   it is in, or what happens next.

---

## What is in the system

| Container | Port (host) | Owns | Responsibility |
|---|---|---|---|
| `localstack` | 4666 | – | DynamoDB, EventBridge, SQS and IAM: the whole cloud, locally |
| `bootstrap` | – | – | Creates the tables, bus, rules and queues, then exits (the CDK stack's local stand-in) |
| `order-service` | 9280 | `maltashop-order-events`, `maltashop-order-view` | REST entry point, the event store, and the projector that maintains the read model |
| `workflow-service` | 9284 | `maltashop-executions`, `maltashop-tasks` | Interprets the state machine; owns the sequence and the compensation, and no business rules |
| `inventory-service` | 9281 | `maltashop-inventory` | Holds, releases and commits stock |
| `payment-service` | 9282 | `maltashop-payments` | The only caller of the card provider; stores a reference, never a card number |
| `notification-service` | 9283 | `maltashop-notifications` | Subscribes to outcomes; nothing waits for it |

Each service reads and writes **its own tables only**. In AWS that is enforced by
the function's execution role rather than by convention.

### The flow

```
POST /orders ─► order-service
                 │  append OrderPlaced to the event store (seq 1)
                 └─► StartExecution ─► workflow-service
                                        │
            ┌───────── task token ──────┤ ReserveStock  ──► inventory-service
            │                           │                      │ holds stock
            └──── SendTaskSuccess ◄─────┘                      ▼
                                        │  Choice: RESERVED?   publishes StockReserved
            ┌───────── task token ──────┤ AuthorisePayment ─► payment-service
            └──── SendTaskSuccess ◄─────┘
                                        │  Choice: AUTHORISED?
                        ┌───────────────┴───────────────┐
                 ConfirmOrder                      ReleaseStock  (compensation)
                        │                                │
                 putEvents OrderConfirmed          then CancelOrder
                        │
      EventBridge rules ├─► order-service   (append to the stream, re-project)
                        ├─► notification-service (e-mail)
                        └─► inventory-service (turn the hold into a deduction)
```

Every arrow out of the workflow's `putEvents` states is a **rule**, not a call.
Adding the recommendation pipeline or the thirty partner feeds is a rule and a
queue; no producer changes.

---

## Running it

Requirements: Docker with Compose v2, plus `curl`, `jq` and `uuidgen`.

```bash
git clone <this repository>
cd maltashop-eventcore
cp .env.example .env          # optional; the defaults work
docker compose up --build -d --wait
./scripts/smoke_test.sh
```

Stop and remove everything, volumes included:

```bash
docker compose down -v
```

### Try it by hand

```bash
# Place an order. The answer comes back before anything downstream has happened.
curl -sS -X POST http://localhost:9280/orders \
  -H 'content-type: application/json' \
  -H 'x-correlation-id: 7f1c0000-1111-2222-3333-444455556666' \
  -H 'idempotency-key: demo-001' \
  -d '{"customer_id":"MT-C-7741","items":[{"sku":"COFFEE-DLX","quantity":1},
                                          {"sku":"KETTLE-TMP","quantity":2}]}' | jq

# The read model (a projection), and the same order folded from its events.
curl -sS "http://localhost:9280/orders/<order_id>" | jq '{state, source, version}'
curl -sS "http://localhost:9280/orders/<order_id>?consistent=true" | jq '{state, source}'

# The raw stream, and the workflow execution that produced it.
curl -sS "http://localhost:9280/orders/<order_id>/events" | jq
curl -sS "http://localhost:9284/executions/<execution_id>" | jq '{status, state, path}'

# Stock, payments and the e-mail that was recorded.
curl -sS http://localhost:9281/stock | jq
curl -sS "http://localhost:9283/notifications?order_id=<order_id>" | jq
```

Two SKUs make the failure paths visible:

* **`MONITOR-27U`** costs €749, above the stub provider's €600 ceiling, so payment
  is declined, `ReleaseStock` runs and the order ends `CANCELLED`;
* **`SOLD-OUT-PRO`** has no stock, so the workflow goes straight to `RejectOrder`
  and payment is never called.

### Endpoints

| Method | Path | Service |
|---|---|---|
| `POST` | `/orders` | order — accepts `Idempotency-Key` and `X-Correlation-Id`; answers `201` with `state: PENDING` |
| `GET` | `/orders/{id}` | order — the read model; `?consistent=true` folds the events instead |
| `GET` | `/orders/{id}/events` | order — the raw event stream |
| `GET` | `/executions/{id}` | workflow — status, current state and the path taken |
| `GET` | `/stock` | inventory — on hand, reserved and available |
| `GET` | `/payments?order_id=` | payment — the decision and the provider reference |
| `GET` | `/notifications?order_id=` | notification — the messages recorded |
| `GET` | `/health/live`, `/health/ready` | all |

---

## Environment variables

Everything is read from the environment at start-up (12-factor III); nothing is
read from a file. `.env.example` is the complete list.

| Variable | Default | Meaning |
|---|---|---|
| `SERVICE_NAME` | per container | The `service` field on every log line |
| `SERVICE_VERSION` | `1.2.0` | Stamped on logs, so a bad release stands out |
| `ENVIRONMENT` | `local` | `local`, `staging` or `production` |
| `LOG_LEVEL` | `info` | `debug`, `info`, `warn`, `error` |
| `PORT` | 8080–8084 | Port inside the container |
| `AWS_ENDPOINT_URL` | LocalStack | **Unset in AWS** — the single difference between local and cloud |
| `AWS_REGION` | `eu-south-1` | Milan, the closest region to Malta |
| `EVENT_BUS` | `maltashop-bus` | The custom EventBridge bus |
| `WORKFLOW_URL` | workflow-service | Where `SendTaskSuccess` is posted; the Step Functions API in AWS |
| `CARD_CEILING_EUR` | `600` | The stub provider's limit, used to show compensation |
| `STATE_MACHINE` | `/app/contracts/place-order.asl.json` | The ASL definition the engine runs |

In AWS none of the credentials exist: every function assumes its execution role.

---

## How consistency is kept without a distributed transaction

| Problem | Mechanism | Where |
|---|---|---|
| Two writers claiming one position in the stream | **Conditional append** on `(order_id, seq)` | `maltashop/eventstore.py` |
| The customer presses "Pay" twice | **Idempotency key** stored as its own item | `order-service/app/main.py` |
| SQS delivers a message twice | **Per-consumer inbox**: `claim_once` writes `<service>#<event_id>` once | `maltashop/worker.py` |
| A worker's task is redelivered | The handler answers with the **decision already taken** rather than retaking it | `inventory`, `payment` |
| Stock held for an order that then fails | **Compensating state** `ReleaseStock`, declared in the workflow | `contracts/place-order.asl.json` |
| A worker never answers | **`TimeoutSeconds` and `Catch`** on every waiting state, swept every five seconds | `workflow-service/app/engine.py` |
| SQS delivers facts out of order | The **fold never walks an order backwards** and never moves a terminal one | `maltashop/eventstore.py` |

## Tests

```bash
docker build -f Dockerfile.test -t maltashop/eventcore-test:local .
docker run --rm -v "$PWD":/w -w /w maltashop/eventcore-test:local python -m pytest tests -q
./scripts/smoke_test.sh        # needs the stack running
./scripts/run_pipeline.sh      # every pipeline phase, locally
```

* **Unit** — the fold, including out-of-order delivery and both failure paths
  (`tests/test_fold.py`); the states-language engine's paths, parameter expansion
  and choices (`tests/test_engine.py`). No AWS, no network.
* **Contract** — `tests/test_contract.py` expands the workflow's own `ConfirmOrder`
  parameters and validates the result against the schema the *consumer* owns, so a
  field renamed in the state machine fails the producer's build.
* **Integration** — `scripts/smoke_test.sh` drives the whole platform, including
  both failure paths and the event-sourcing round trip.

## Layout

```
buildspec.yml            CodeBuild: verify, build once, integration
appspec.yml              CodeDeploy: the canary and the alarms that reverse it
contracts/               the state machine, and the schema the consumer owns
maltashop/               shared platform: config, logging, AWS, event store, worker loop
<service>/app/           one handler package per service
scripts/                 bootstrap, smoke test, local pipeline
tests/                   unit and contract tests
docs/adr/                architecture decision records
evidence/                screenshots and transcripts of the demonstration
diagrams/                the report's figures, drawn as SVG and rendered to PNG
report/                  the build pipeline for the Unit 5 report
```
