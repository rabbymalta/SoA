# ADR-0002: Honeycomb as the observability platform

* Status: accepted
* Date: 2026-04-28
* Deciders: Lead Solutions Architect, Operations lead

## Context

Logs are files on two virtual machines, there is no alerting, and customers report
incidents first. The architecture being adopted makes this worse before it makes it
better: a single checkout becomes one HTTP request, one workflow execution, three
queue hops and four handler invocations. Aggregate dashboards will show that the
average is fine while a particular customer's order is stuck, and the March incident
showed that the expensive part of an outage is working out *which* component is at
fault, not fixing it.

## Decision

Adopt **Honeycomb** as the primary observability platform, with services
instrumented using **OpenTelemetry** and every span carrying wide, high-cardinality
attributes: `correlation_id`, `order_id`, `customer_id`, `sku`, `workflow_state`
and `cold_start`. CloudWatch is kept for infrastructure metrics and for the alarms
that CodeDeploy reads during a canary.

## Alternatives rejected

| Option | Why it was rejected |
|---|---|
| **CloudWatch Logs Insights and X-Ray alone** | Already present, already paid for, and genuinely sufficient for metrics. Rejected as the primary tool because querying by an arbitrary attribute across services is slow and awkward, and X-Ray's sampling makes the rare bad order the one most likely to be missing. |
| **Datadog** | The strongest product on the list and the easiest to adopt. Rejected on price: metered per host, per ingested gigabyte and per indexed span, it was modelled as the largest single item in the tooling budget at eleven times peak traffic, and the pricing grows with precisely the success being planned for. |
| **Grafana Cloud with Loki and Tempo** | Cheaper and open at the instrumentation layer, but the query model is log-and-metric shaped. The question this platform most needs to answer — "show me every order where the workflow stopped in AuthorisePayment, grouped by customer" — is a high-cardinality question, and that is the one thing it does least well. |

## Criteria used

Answering a question about one order across every component (weight 3), no
sampling away of rare failures (3), cost at eleven times peak (3), neutral
instrumentation so the backend can change (3), effort to operate (2).

## Consequences

**Good.** One trace shows the whole order, including the time spent waiting on a
queue, and because the attributes are arbitrary the team can ask a question it did
not anticipate when it instrumented. OpenTelemetry means the backend is replaceable
without touching handler code, which is the real insurance being bought.

**Bad.** A recurring invoice the CFO sees monthly, priced per event, so a careless
debug span in a hot path costs money. High-cardinality attributes are also exactly
where personal data leaks, so the Collector's redaction rules become a GDPR control
and must be reviewed whenever an attribute is added.

**Debt accepted.** Only the five checkout components are instrumented at launch. The
catalogue and customer functions emit logs but no spans, so a trace stops at their
edge until phase two. Trace retention is 60 days, which is shorter than the audit
window the finance team would prefer.
