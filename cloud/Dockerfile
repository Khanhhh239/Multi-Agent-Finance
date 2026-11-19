FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    AGENT4_CLOUD_MODE=1 \
    AGENT4_DEMO_MODE=0 \
    AGENT4_SELECTION_CONFIG=/app/config/selection_cloud.yaml \
    AGENT4_MAX_CONCURRENT_QUERIES=1 \
    AGENT4_QUERY_TIMEOUT_MS=5000

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin agent4 \
    && mkdir -p /app/.cache /tmp/agent4 \
    && chown -R agent4:agent4 /app /tmp/agent4

COPY agent4/requirements-cloud.txt /app/requirements-cloud.txt
RUN python -m pip install --no-cache-dir -r /app/requirements-cloud.txt

# Copy only the cloud runtime and immutable configuration. Agent 1–3 code, local
# models and datagen dependencies are deliberately absent from this image.
COPY agent4/agent4 /app/agent4
COPY agent4/config /app/config
COPY cloud /app/cloud
COPY database /app/database

RUN chown -R agent4:agent4 /app
USER agent4

EXPOSE 10000
CMD ["sh", "/app/cloud/entrypoint.sh"]
