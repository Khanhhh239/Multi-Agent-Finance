FROM python:3.12-slim AS dependencies

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY shared/finance_input /app/shared/finance_input
COPY agent1/requirements.txt agent1/requirements-service.txt /app/agent1/
COPY agent2/requirements.txt /app/agent2/
COPY agent3/agent3_tax_compliance/requirements.txt /app/agent3/agent3_tax_compliance/
COPY agent4/requirements-cloud.txt /app/agent4/

RUN python -m venv /opt/portal-venv \
    && /opt/portal-venv/bin/pip install -e /app/shared/finance_input cryptography \
    && python -m venv /app/agent1/.venv \
    && cd /app/agent1 && .venv/bin/pip install -r requirements-service.txt \
    && python -m venv /app/agent2/.venv \
    && cd /app/agent2 && .venv/bin/pip install -r requirements.txt cryptography \
    && python -m venv /app/agent3/agent3_tax_compliance/.venv \
    && cd /app/agent3/agent3_tax_compliance && .venv/bin/pip install -r requirements.txt \
    && python -m venv /app/agent4/.venv \
    && cd /app/agent4 && .venv/bin/pip install -r requirements-cloud.txt

FROM node:22-alpine AS agent3-ui
WORKDIR /repo
COPY design /repo/design
COPY agent3/agent3_tax_compliance/webui /repo/agent3/agent3_tax_compliance/webui
WORKDIR /repo/agent3/agent3_tax_compliance/webui
RUN npm ci && npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/portal-venv \
    PATH=/opt/portal-venv/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 libxml2 libxslt1.1 tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin maf-demo

WORKDIR /app
COPY --from=dependencies /opt/portal-venv /opt/portal-venv
COPY --from=dependencies /app/agent1/.venv /app/agent1/.venv
COPY --from=dependencies /app/agent2/.venv /app/agent2/.venv
COPY --from=dependencies /app/agent3/agent3_tax_compliance/.venv /app/agent3/agent3_tax_compliance/.venv
COPY --from=dependencies /app/agent4/.venv /app/agent4/.venv

COPY portal /app/portal
COPY shared /app/shared
COPY agent1 /app/agent1
COPY agent2 /app/agent2
COPY agent3/agent3_tax_compliance /app/agent3/agent3_tax_compliance
COPY agent4 /app/agent4
COPY agent4_chat /app/agent4_chat
COPY design /app/design
COPY database /app/database
COPY --from=agent3-ui /repo/agent3/agent3_tax_compliance/src/assistant/static /app/agent3/agent3_tax_compliance/src/assistant/static
COPY deploy/azure-vm/portal-config.json /app/deploy/azure-vm/portal-config.json
COPY deploy/azure-vm/entrypoint.sh /app/deploy/azure-vm/entrypoint.sh

RUN mkdir -p /state/portal /state/agent1 /state/agent2 /state/agent3 /state/demo \
    && chmod +x /app/deploy/azure-vm/entrypoint.sh \
    && chown -R maf-demo:maf-demo /app /state

USER maf-demo
EXPOSE 8800 8011 8640
ENTRYPOINT ["tini", "--"]
CMD ["/app/deploy/azure-vm/entrypoint.sh"]
