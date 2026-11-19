#!/bin/sh
set -eu

python /app/cloud/prepare_artifact.py
exec uvicorn agent4.api:create_cloud_app --factory --host 0.0.0.0 --port "${PORT:-10000}" --workers 1
