# syntax=docker/dockerfile:1.7
# One image, five roles.
#
# Every handler in this repository is deployed to AWS as a Lambda function from a
# single bundle, so the prototype mirrors that: one image contains all the handler
# packages and the Compose `command` chooses which one this container runs. The
# build stage compiles wheels so that no compiler ever reaches the runtime image.

# ---------- stage 1: resolve and build wheels --------------------------------
FROM python:3.12.7-slim-bookworm AS wheels
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- stage 2: the image that ships ------------------------------------
FROM python:3.12.7-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin handler
COPY --from=wheels /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt && rm -rf /wheels
COPY --chown=handler:handler maltashop ./maltashop
COPY --chown=handler:handler order-service/app ./order_service
COPY --chown=handler:handler workflow-service/app ./workflow_service
COPY --chown=handler:handler inventory-service/app ./inventory_service
COPY --chown=handler:handler payment-service/app ./payment_service
COPY --chown=handler:handler notification-service/app ./notification_service
COPY --chown=handler:handler scripts ./scripts
COPY --chown=handler:handler contracts ./contracts
# Runs as an unprivileged account with no login shell and no home directory.
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT:-8080}/health/ready" || exit 1
