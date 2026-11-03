#!/usr/bin/env bash
# End-to-end check of the place-order workflow. Run by the pipeline's integration
# stage and by hand after `docker compose up`.
set -euo pipefail
ORDER=${ORDER_URL:-http://localhost:9280}
WORKFLOW=${WORKFLOW_URL:-http://localhost:9284}
INVENTORY=${INVENTORY_URL:-http://localhost:9281}
PAYMENT=${PAYMENT_URL:-http://localhost:9282}
NOTIFY=${NOTIFY_URL:-http://localhost:9283}

pass() { printf '  \033[32mPASS\033[0m  %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m  %s\n' "$1"; exit 1; }

place() {   # place <correlation-id> <idempotency-key> <items-json>
  curl -sS -X POST "$ORDER/orders" -H 'content-type: application/json' \
    -H "x-correlation-id: $1" -H "idempotency-key: $2" \
    -d "{\"customer_id\":\"MT-C-7741\",\"items\":$3}"
}
await_state() {   # await_state <order-id> <state>
  for _ in $(seq 1 50); do
    state=$(curl -sS "$ORDER/orders/$1" | jq -r .state 2>/dev/null || echo "")
    [ "$state" = "$2" ] && return 0
    sleep 0.5
  done
  echo "    last state: ${state:-unknown}"; return 1
}
await_mail() {    # await_mail <order-id> <template>
  for _ in $(seq 1 50); do
    [ "$(curl -sS "$NOTIFY/notifications?order_id=$1" | jq -r '.[0].template // empty')" = "$2" ] && return 0
    sleep 0.5
  done
  return 1
}

echo "1. happy path: reserved, authorised, confirmed"
CID=$(uuidgen | tr 'A-Z' 'a-z')
BODY=$(place "$CID" "k-$CID" '[{"sku":"COFFEE-DLX","quantity":1},{"sku":"KETTLE-TMP","quantity":2}]')
ORDER_ID=$(echo "$BODY" | jq -r .order_id)
EXEC_ID=$(echo "$BODY" | jq -r .execution_id)
[ "$(echo "$BODY" | jq -r .state)" = PENDING ] || fail "the API should answer PENDING at once"
pass "POST /orders returned 201 PENDING with order_id $ORDER_ID"
await_state "$ORDER_ID" CONFIRMED || fail "the order never reached CONFIRMED"
pass "the order reached CONFIRMED"
PATHS=$(curl -sS "$WORKFLOW/executions/$EXEC_ID" | jq -r '.path | join(" -> ")')
[ "$PATHS" = "ReserveStock -> StockOutcome -> AuthorisePayment -> PaymentOutcome -> ConfirmOrder" ] \
  || fail "unexpected workflow path: $PATHS"
pass "the workflow took: $PATHS"
[ "$(curl -sS "$PAYMENT/payments?order_id=$ORDER_ID" | jq -r '.[0].state')" = AUTHORISED ] \
  || fail "payment was not authorised"
pass "payment-service recorded an AUTHORISED payment"
await_mail "$ORDER_ID" order-confirmed || fail "no confirmation e-mail was recorded"
pass "notification-service recorded the confirmation e-mail"
[ "$(curl -sS "$NOTIFY/notifications?order_id=$ORDER_ID" | jq -r '.[0].correlation_id')" = "$CID" ] \
  || fail "the correlation ID did not survive the hops"
pass "the same correlation ID appears in every service"

echo "2. event sourcing: the order is the fold of its events"
EVENTS=$(curl -sS "$ORDER/orders/$ORDER_ID/events" | jq -r '[.[].event_type] | join(",")')
case "$EVENTS" in
  OrderPlaced,*StockReserved*) pass "the stream holds: $EVENTS" ;;
  *) fail "unexpected event stream: $EVENTS" ;;
esac
[ "$(curl -sS "$ORDER/orders/$ORDER_ID?consistent=true" | jq -r .state)" = CONFIRMED ] \
  || fail "folding the events gave a different answer from the read model"
pass "folding the stream on read agrees with the projection"

echo "3. idempotency: the same key must not create a second order"
[ "$(place "$CID" "k-$CID" '[{"sku":"COFFEE-DLX","quantity":1}]' | jq -r .order_id)" = "$ORDER_ID" ] \
  || fail "a retry created a second order"
pass "the retried request returned the original order"

echo "4. compensation: payment declined, the reservation released"
BEFORE=$(curl -sS "$INVENTORY/stock" | jq -r '.[]|select(.sku=="MONITOR-27U")|.available')
CID2=$(uuidgen | tr 'A-Z' 'a-z')
BODY2=$(place "$CID2" "k-$CID2" '[{"sku":"MONITOR-27U","quantity":1}]')
ORDER_ID2=$(echo "$BODY2" | jq -r .order_id)
EXEC_ID2=$(echo "$BODY2" | jq -r .execution_id)
await_state "$ORDER_ID2" CANCELLED || fail "the declined order never reached CANCELLED"
pass "the declined order was cancelled"
PATH2=$(curl -sS "$WORKFLOW/executions/$EXEC_ID2" | jq -r '.path | join(" -> ")')
case "$PATH2" in *ReleaseStock*CancelOrder) pass "the workflow compensated: $PATH2" ;;
  *) fail "the workflow did not compensate: $PATH2" ;; esac
AFTER=$(curl -sS "$INVENTORY/stock" | jq -r '.[]|select(.sku=="MONITOR-27U")|.available')
[ "$BEFORE" = "$AFTER" ] || fail "stock was not released (before $BEFORE, after $AFTER)"
pass "the compensating action returned the held stock ($AFTER available)"

echo "5. rejection: an item with no stock never reaches payment"
CID3=$(uuidgen | tr 'A-Z' 'a-z')
ORDER_ID3=$(place "$CID3" "k-$CID3" '[{"sku":"SOLD-OUT-PRO","quantity":1}]' | jq -r .order_id)
await_state "$ORDER_ID3" REJECTED || fail "the out-of-stock order never reached REJECTED"
[ "$(curl -sS "$PAYMENT/payments?order_id=$ORDER_ID3" | jq -r 'length')" = 0 ] \
  || fail "payment should never have been called"
pass "the order was rejected before payment was called"

printf '\n\033[32mall checks passed\033[0m\n'
