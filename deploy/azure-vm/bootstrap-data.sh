#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
mkdir -p "$HERE/state/demo" "$HERE/state/agent3"

warehouse="$REPO/portal/workspace/datasets/enterprise-x10-v3-smoke/warehouse.duckdb"
law_db="$REPO/agent3/agent3_tax_compliance/data/lawbase/legal_corpus.sqlite3"

if [ -f "$warehouse" ]; then
  cp -n "$warehouse" "$HERE/state/demo/warehouse.duckdb"
  echo "Copied Agent 4 demo warehouse."
else
  echo "Agent 4 warehouse not found at $warehouse; copy it to deploy/azure-vm/state/demo/warehouse.duckdb before starting." >&2
fi

if [ -f "$law_db" ]; then
  cp -n "$law_db" "$HERE/state/agent3/legal_corpus.sqlite3"
  echo "Copied Agent 3 legal corpus."
else
  echo "Agent 3 legal corpus not found at $law_db; copy it to deploy/azure-vm/state/agent3/legal_corpus.sqlite3 before starting." >&2
fi
