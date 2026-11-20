#!/bin/sh
set -eu

mkdir -p /state/home /state/portal /state/agent1 /state/agent2 /state/agent2/secrets /state/agent3/workspaces /state/agent3/law-cache /state/demo
chmod 700 /state/agent2/secrets

# Agent 2's investigation queue (the "Phân tích" button) needs a release store sealed with a
# server-only key. Create both once; later starts reuse them. Back up state/agent2/secrets with
# the databases: the release store cannot be read without this key.
A2_KEY=/state/agent2/secrets/node-state.key
A2_RELEASE=/state/agent2/release-runtime.json
if [ ! -f "$A2_KEY" ]; then
  (cd /app/agent2 && /app/agent2/.he-venv/bin/python -B -m experiments.he_inference.key_manager create --output "$A2_KEY" >/dev/null)
fi
if [ ! -f "$A2_RELEASE" ]; then
  printf '{"version":"pipeline-release-runtime/1.0.0","release_db":"/state/agent2/pipeline-releases.sqlite3","node_state_key_file":"%s"}\n' "$A2_KEY" > "$A2_RELEASE"
fi

if [ -n "${AGENT3_LAW_DB:-}" ] && [ ! -f "$AGENT3_LAW_DB" ] \
   && [ -f /app/agent3/agent3_tax_compliance/data/lawbase/legal_corpus.sqlite3 ]; then
  mkdir -p "$(dirname "$AGENT3_LAW_DB")"
  cp /app/agent3/agent3_tax_compliance/data/lawbase/legal_corpus.sqlite3 "$AGENT3_LAW_DB"
fi

exec python -m portal.server --start-all
