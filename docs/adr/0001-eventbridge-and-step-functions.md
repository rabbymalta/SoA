# ADR-0001: EventBridge for integration, Step Functions for coordination

* Status: accepted
* Date: 2026-04-14
* Deciders: Lead Solutions Architect, Data lead, Operations lead

## Context

MaltaShop needs two different things that are often confused. It needs **integration**:
one order event reaching the notification handler, the recommendation pipeline and
thirty partner feeds, with new consumers added without touching a producer. And it
needs **coordination**: a place-order sequence across Order, Inventory and Payment
that has an explicit compensating path and must be auditable when it fails. The
team is twelve developers and two operations staff, none of whom has run a broker
or a cluster in production.

## Decision

Use **Amazon EventBridge** as the integration backbone — one custom bus,
`maltashop-bus`, with a rule per consumer delivering into that consumer's own SQS
queue — and **AWS Step Functions** as the coordinator, with the place-order saga
declared in Amazon States Language and workers answering through the
`waitForTaskToken` callback pattern.

## Alternatives rejected

| Option | Why it was rejected |
|---|---|
| **Amazon MSK or self-managed Kafka** | The right answer once the browsing stream needs months of replay, but a cluster to size, patch and rebalance is the single largest operational commitment on the table, and two staff cannot carry it in the same year as everything else. |
| **SNS plus SQS only** | Cheaper per message and perfectly adequate for fan-out, but it has no content-based routing, no schema registry and no archive-and-replay, so every new consumer becomes a change to the publisher's topic list. |
| **An orchestrator written inside the Order service** | No new infrastructure, and the cheapest thing to build. Rejected because the sequence then lives in application code that must be deployed, scaled and debugged with the Order service, and because "where did order 8842 stop?" becomes a log search rather than a console. |
| **Choreography with no coordinator** | The least infrastructure of all, but the compensating path becomes an emergent property of who subscribes to what, and the case explicitly requires an auditable undo for money movements. |

## Criteria used

Operational effort for two staff (weight 3), adding a consumer without touching a
producer (3), an auditable and visual failure path (3), cost at eleven times peak
(2), replay (2), and how easily each could be replaced later (2).

## Consequences

**Good.** A new consumer is a rule and a queue, which is how the thirty partner
feeds and the recommendation pipeline are added without a release of the Order
service. The saga is a declaration rather than code, so a reviewer can read the
failure path in one file, and the Step Functions console shows every execution and
exactly which state it stopped in. Neither service has a server to patch.

**Bad.** Both are proprietary AWS services, and the states language is a dialect the
team must learn. EventBridge's at-least-once delivery and lack of ordering push
real work onto every consumer, which is why idempotency appears in every handler.
Per-state-transition pricing means a chatty workflow is a line on the invoice.

**Debt accepted.** The prototype interprets the same ASL file locally instead of
running Step Functions, because it is a managed service with no container. The
callback protocol is reproduced faithfully, but timeout and heartbeat behaviour is
only approximated, and that difference must be exercised in a staging environment
before launch.
