#!/bin/sh
set -eu

mkdir -p /state/home /state/portal /state/agent1 /state/agent2 /state/agent3/workspaces /state/agent3/law-cache /state/demo

if [ -n "${AGENT3_LAW_DB:-}" ] && [ ! -f "$AGENT3_LAW_DB" ] \
   && [ -f /app/agent3/agent3_tax_compliance/data/lawbase/legal_corpus.sqlite3 ]; then
  mkdir -p "$(dirname "$AGENT3_LAW_DB")"
  cp /app/agent3/agent3_tax_compliance/data/lawbase/legal_corpus.sqlite3 "$AGENT3_LAW_DB"
fi

exec python -m portal.server --start-all
