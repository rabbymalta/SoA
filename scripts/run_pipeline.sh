#!/usr/bin/env bash
# Runs the pipeline's verify, build and integration phases on this machine, using
# the same commands buildspec.yml runs on CodeBuild. Used to produce the evidence
# screenshot when a hosted run is not to hand.
set -uo pipefail
cd "$(dirname "$0")/.."
TEST_IMAGE=maltashop/eventcore-test:local
ok=0; failed=0
stage() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
step() {
  local label=$1; shift
  local start; start=$(date +%s)
  if output=$("$@" 2>&1); then
    printf '  PASS  %-48s %4ss\n' "$label" "$(( $(date +%s) - start ))"; ok=$((ok+1))
  else
    printf '  FAIL  %-48s\n%s\n' "$label" "$output"; failed=$((failed+1))
  fi
}
in_python() { docker run --rm -v "$PWD":/w -w /w "$TEST_IMAGE" sh -c "$1"; }

stage "phase 1  verify"
step "test image builds with pinned tooling" bash -c "docker build -q -f Dockerfile.test -t $TEST_IMAGE ."
step "ruff: style and obvious defects" in_python "ruff check ."
step "bandit: insecure patterns in handler code" in_python "bandit -q -r maltashop order-service workflow-service inventory-service payment-service notification-service"
step "unit tests: the fold and the engine" in_python "python -m pytest tests/test_fold.py tests/test_engine.py -q"
step "contract test: OrderConfirmed v1" in_python "python -m pytest tests/test_contract.py -q"
step "the state machine is valid JSON" in_python "python -c \"import json;json.load(open('contracts/place-order.asl.json'))\""

stage "phase 2  build once"
step "handler bundle image" bash -c "docker build -q -t maltashop/eventcore:local ."

stage "phase 3  integration"
step "platform healthy (LocalStack + 5 handlers)" bash -c "docker compose ps --format '{{.Service}} {{.Status}}' | grep -q healthy"
step "place-order workflow, both failure paths" ./scripts/smoke_test.sh

printf '\n'
if [ "$failed" -eq 0 ]; then printf '\033[32mpipeline passed: %s checks, 0 failures\033[0m\n' "$ok"
else printf '\033[31mpipeline failed: %s failures\033[0m\n' "$failed"; exit 1; fi
