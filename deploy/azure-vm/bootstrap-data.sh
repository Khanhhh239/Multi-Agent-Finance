#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO=$(CDPATH= cd -- "$HERE/../.." && pwd)
mkdir -p "$HERE/state/demo" "$HERE/state/agent2" "$HERE/state/agent2/secrets" "$HERE/state/agent3" "$HERE/state/portal"
chmod 700 "$HERE/state/agent2/secrets"

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

agent2_files="snapshots-v2.sqlite3 models-v2.sqlite3 case-queue.sqlite3 remediation.sqlite3 analysis-bindings.json"
agent2_ready=1
for name in $agent2_files; do
  if [ ! -f "$HERE/state/agent2/$name" ]; then agent2_ready=0; fi
done
if [ ! -f "$HERE/state/portal/agent2_access.json" ]; then agent2_ready=0; fi
if [ "$agent2_ready" -eq 1 ]; then
  chmod 600 "$HERE/state/agent2"/*.sqlite3 "$HERE/state/agent2/analysis-bindings.json" "$HERE/state/portal/agent2_access.json"
  echo "Agent 2 demo data and access policy are present."
else
  echo "Agent 2 demo state is missing. Run prepare-agent2-state.py on the source checkout and transfer its ignored state files here." >&2
fi
