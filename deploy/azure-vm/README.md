# Public demo on one Azure VM

The step-by-step deployment checklist is [TRIEN_KHAI.md](TRIEN_KHAI.md) (Vietnamese). This README explains how the
setup is built; when the two differ, follow TRIEN_KHAI.md.

## What runs on the VM

Three containers from [compose.yaml](compose.yaml):

| Container | Role |
|---|---|
| `maf-demo` | The Portal (port 8800), which starts Agents 1–4 as separate Python processes, plus the Agent 2 training station (8890). Built on the team machine and loaded with `docker load`; the VM never builds it. |
| `maf-demo-ollama` | Local embedding model `bge-m3:567m` for Agent 3 (legal search) and Agent 4 (metric selection). Pulled into the `ollama_models` volume on its first start. No paid embedding API is used. |
| `maf-demo-caddy` | HTTPS (Let's Encrypt) and logins. It is the only container that publishes ports (80 and 443). |

All four agents work with one simulated company, Minh Phát (MPX10, tax code 0999999905), because the Agent 4 ledger
warehouse only holds that company. `MAF_LOCK_COMPANY=1` keeps its code and tax code fixed on the site.

## Public URLs and logins

| Component | URL | Login |
|---|---|---|
| Portal | `https://<PORTAL_HOST>/` | `SITE_USER` |
| Agent 2 | `https://<PORTAL_HOST>/agent2/` | `SITE_USER` |
| Agent 4 | `https://<PORTAL_HOST>/agent4/` | `SITE_USER` |
| Agent 2 training station | `https://<PORTAL_HOST>/station/` | `STATION_USER` |
| Agent 1 | `https://<AGENT1_HOST>/workspace` | none (shown inside the Portal) |
| Agent 3 | `https://<AGENT3_HOST>/` | none (shown inside the Portal); its admin page uses `AGENT3_ADMIN_PASSWORD` |

Agent 1 and Agent 3 have their own hostnames because their browser interfaces make root-relative API requests. They
stay without a Caddy login because the Portal embeds them in iframes. Judges should only get the Portal URL: Agent 1
receives a short-lived Portal ticket and Agent 2 checks the Portal session, so both need to be opened from the Portal.

Without your own domain, use sslip.io with the IP written with dashes, for example
`portal.20-46-171-174.sslip.io`, `agent1.20-46-171-174.sslip.io` and `agent3.20-46-171-174.sslip.io`.

## Settings

The whole project uses one settings file: `.env` at the repository root (template: `../../.env.example`). Every
compose command runs from `deploy/azure-vm` with `--env-file ../../.env`; the same file becomes the app container's
environment. `.dockerignore` keeps every `.env` out of the image.

| Variables | Used for |
|---|---|
| `PORTAL_HOST`, `AGENT1_HOST`, `AGENT3_HOST` | The three hostnames (DNS A records pointing to the VM). |
| `MAF_UID`, `MAF_GID` | Output of `id -u` / `id -g` on the VM; the container runs as this user so it can write `state/`. |
| `AGENT3_LLM_API_KEY`, `AGENT4_LLM_API_KEY` | Groq LLM (`qwen/qwen3.8-27b`) for Agent 3 and Agent 4. |
| `AGENT3_RERANK_API_KEY` | Cohere reranker for legal search (optional; without it the rerank step is skipped). |
| `AGENT3_ADMIN_PASSWORD` | Fixed password of the Agent 3 admin page. |
| `STATION_USER`, `STATION_PASSWORD_HASH` | Training station login. |
| `SITE_USER`, `SITE_PASSWORD_HASH` | Shared reviewer login for the Portal host. |
| `AGENT3_EMBED_*`, `AGENT4_EMBED_*` | Team machine only (local Ollama at `127.0.0.1:11434`). On the VM, `compose.yaml` overrides them to point at the `ollama` container. |

Create a password hash with `docker run --rm caddy:2-alpine caddy hash-password --plaintext '<password>'` and keep it in
single quotes in `.env` (it contains `$`). Compose refuses to start while a hostname, `STATION_*` or `SITE_*` value is
missing.

The embedding model is written in two places that must match: `AGENT3_EMBED_MODEL` in the root `.env` (used when the
team machine embeds the legal corpus that goes into the image) and `x-embed-model` in `compose.yaml` (used on the VM).
If they differ, Agent 3 discards the corpus vectors and embeds all chunks again on the VM CPU at first start.

## Files in this folder

| File | Purpose |
|---|---|
| `compose.yaml`, `Caddyfile` | The only two files the VM needs besides the root `.env`, the image and `state/`. |
| `Dockerfile`, `entrypoint.sh`, `portal-config.json` | Image build (team machine) and container start. |
| `collect-state.py` | Builds `state/` from a checkout where `run_web.bat` has run: the full Minh Phát warehouse for Agent 4, Agent 2 snapshots, fitted models and access policy, the MPX10 company profile and the fixed data-intake password (`SoSon@2026`). It calls `prepare-agent2-state.py`. |
| `prepare-agent2-state.py` | Agent 2 export used by `collect-state.py`. |
| `bootstrap-data.sh` | Older helper (copies the *smoke* warehouse); replaced by `collect-state.py`, not part of the current steps. |
| `TRIEN_KHAI.md` | The deployment checklist. |

`state/` (ignored by Git) holds everything the demo writes: Portal workspace, Agent 1 data, Agent 2 databases and
keys, Agent 3 workspaces and legal corpus, the Agent 4 warehouse and its embedding index. The team packs a clean copy as
`state-pristine.tgz`; restoring it returns the demo to its starting point. The legal corpus is not in `state-pristine`:
on first start the container copies it from the image to `state/agent3/` (only when that file is missing).

## Deployment outline

The commands are in TRIEN_KHAI.md. In short:

1. Team machine: embed the legal corpus with the local Ollama model, build `maf-demo:latest`, `docker save` it, and pack
   `state/` as `state-pristine.tgz`.
2. Azure: Ubuntu 24.04 x86-64 (the current VM is a burstable Standard_B4s_v2, 4 vCPU / 16 GB; Standard_D8s_v5 is safer under load), at least 128 GB disk, static public
   IP. The network security group allows inbound 80 and 443 only, with SSH (22) limited to the team's IP. Install Docker
   Engine with the Compose plugin.
3. Copy the image, `state-pristine.tgz`, the root `.env`, `compose.yaml` and `Caddyfile` to the VM
   (`~/soson/.env` and `~/soson/deploy/azure-vm/`).
4. On the VM: `docker load`, unpack `state/`, `docker compose --env-file ../../.env -f compose.yaml up -d --no-build`.

To change an API key or password later, edit `~/soson/.env` and run `up -d --no-build` again; `docker compose restart`
does not reload the file. The VM needs outbound HTTPS for the LLM APIs, Docker Hub (Caddy and Ollama images), the
Ollama model registry and Let's Encrypt.

## Scope and limits

This is a competition-demo setup, not a production security or availability profile. All reviewers share one site and
see each other's uploads; only simulated data should be loaded. Agent 2's joint training through the station uses CKKS
(TenSEAL) inside the Agent 2 process. Concrete HE analysis is not available on the web build: it needs Linux-generated
circuit bundles, key contexts and worker configs. HE keys on the VM are owner-only files under `state/agent2/secrets`;
host root can read them, so use Azure Key Vault for anything beyond the demo.

After the competition, run `docker compose --env-file ../../.env -f compose.yaml down`, then deallocate or delete the VM
and its disk to stop charges.
