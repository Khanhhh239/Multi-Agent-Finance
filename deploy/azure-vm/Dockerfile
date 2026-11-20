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
COPY agent2/requirements.txt agent2/requirements-he.txt agent2/requirements-he4-linux.txt /app/agent2/
COPY agent3/agent3_tax_compliance/requirements.txt /app/agent3/agent3_tax_compliance/
COPY agent4/requirements-cloud.txt /app/agent4/

# Trim the image-only copies of the requirement files (the repo files stay unchanged):
# - Agent 1: drop dev/research tools the service never imports, and use the CPU-only
#   xgboost wheel (same `import xgboost`, without the ~300 MB nvidia-nccl dependency).
# - Agent 3: drop test-only packages.
RUN sed -i -E '/^(pytest|ruff|optuna|matplotlib)==/d; s/^xgboost==/xgboost-cpu==/' /app/agent1/requirements.txt \
    && sed -i -E '/^(pytest|hypothesis)([<>=!~ ]|$)/d' /app/agent3/agent3_tax_compliance/requirements.txt

# Agent 2 runs its web service from .he-venv as well (see portal-config.json): that venv
# already holds every package from agent2/requirements.txt, so a second copy is not built.
# requirements-he.txt adds TenSEAL, which the CKKS joint-training tab (sme_fraud/he_lr_ckks.py) imports.
RUN python -m venv /opt/portal-venv \
    && /opt/portal-venv/bin/pip install -e /app/shared/finance_input cryptography \
    && python -m venv /app/agent1/.venv \
    && cd /app/agent1 && .venv/bin/pip install -r requirements-service.txt \
    && python -m venv /app/agent2/.he-venv \
    && cd /app/agent2 && .he-venv/bin/pip install -e ../shared/finance_input \
    && .he-venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
    && .he-venv/bin/pip install -r requirements-he.txt -r requirements-he4-linux.txt \
    && python -m venv /app/agent3/agent3_tax_compliance/.venv \
    && cd /app/agent3/agent3_tax_compliance && .venv/bin/pip install -r requirements.txt \
    && python -m venv /app/agent4/.venv \
    && cd /app/agent4 && .venv/bin/pip install -r requirements-cloud.txt

# Shrink the venvs before they are copied into the runtime image (~680 MB):
# - remove the test suites that numpy/scipy/sklearn/pandas/torch/... ship inside their packages;
# - strip debug symbols from native libraries (`strip` comes with build-essential).
# Python modules named tests.py (e.g. jinja2.tests) are files, so `-type d` keeps them.
RUN for venv in /opt/portal-venv /app/agent1/.venv /app/agent2/.he-venv \
        /app/agent3/agent3_tax_compliance/.venv /app/agent4/.venv; do \
      site="$venv/lib/python3.12/site-packages"; \
      find "$site" -depth -type d \( -name tests -o -name test \) -exec rm -rf {} + ; \
      find "$site" -type f -name '*.so*' -exec strip --strip-unneeded {} + 2>/dev/null || true; \
    done

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
# Ownership is set while copying. A later `chown -R /app` would rewrite every file
# into a new layer and store all the venvs in the image twice.
COPY --chown=maf-demo:maf-demo --from=dependencies /opt/portal-venv /opt/portal-venv
COPY --chown=maf-demo:maf-demo --from=dependencies /app/agent1/.venv /app/agent1/.venv
COPY --chown=maf-demo:maf-demo --from=dependencies /app/agent2/.he-venv /app/agent2/.he-venv
COPY --chown=maf-demo:maf-demo --from=dependencies /app/agent3/agent3_tax_compliance/.venv /app/agent3/agent3_tax_compliance/.venv
COPY --chown=maf-demo:maf-demo --from=dependencies /app/agent4/.venv /app/agent4/.venv

COPY --chown=maf-demo:maf-demo portal /app/portal
COPY --chown=maf-demo:maf-demo shared /app/shared
COPY --chown=maf-demo:maf-demo agent1 /app/agent1
# Agent 2: only the web service package and the HE modules it imports (experiments/he_*).
# Docs, examples, scripts, tests, requirement files and local .runtime state stay out of the image.
COPY --chown=maf-demo:maf-demo agent2/sme_fraud /app/agent2/sme_fraud
COPY --chown=maf-demo:maf-demo agent2/experiments /app/agent2/experiments
# Training station web (port 8890): stdlib only; Caddy serves it at https://<PORTAL_HOST>/station/ behind a login.
COPY --chown=maf-demo:maf-demo station/server.py station/index.html station/app.js station/style.css /app/station/
COPY --chown=maf-demo:maf-demo agent3/agent3_tax_compliance /app/agent3/agent3_tax_compliance
COPY --chown=maf-demo:maf-demo agent4 /app/agent4
COPY --chown=maf-demo:maf-demo agent4_chat /app/agent4_chat
COPY --chown=maf-demo:maf-demo design /app/design
COPY --chown=maf-demo:maf-demo database /app/database
COPY --chown=maf-demo:maf-demo --from=agent3-ui /repo/agent3/agent3_tax_compliance/src/assistant/static /app/agent3/agent3_tax_compliance/src/assistant/static
COPY --chown=maf-demo:maf-demo deploy/azure-vm/portal-config.json /app/deploy/azure-vm/portal-config.json
COPY --chown=maf-demo:maf-demo deploy/azure-vm/entrypoint.sh /app/deploy/azure-vm/entrypoint.sh

# Only the parent directories (not recursive) and the empty /state tree change owner here.
RUN mkdir -p /state/portal /state/agent1 /state/agent2 /state/agent3 /state/demo \
    && chmod +x /app/deploy/azure-vm/entrypoint.sh \
    && chown maf-demo:maf-demo /app /app/agent1 /app/agent2 /app/agent3 /app/deploy /app/deploy/azure-vm \
    && chown -R maf-demo:maf-demo /state

USER maf-demo
EXPOSE 8800 8011 8640 8890
ENTRYPOINT ["tini", "--"]
CMD ["/app/deploy/azure-vm/entrypoint.sh"]
