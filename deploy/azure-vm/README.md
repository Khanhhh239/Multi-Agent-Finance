# Public demo on one Azure VM

This profile runs the existing Portal and starts Agents 1–4 as separate Python processes in one app container. Caddy handles HTTPS. Only Caddy publishes ports 80 and 443; the Portal and agent ports stay inside the Compose network.

All four agents have public URLs. Agent 1 and Agent 3 use additional HTTPS hostnames behind Caddy because their browser interfaces make root-relative API requests. Agents 2 and 4 use public paths on the Portal hostname. Sharing the Portal URL is the easiest way for judges to open every agent with the right session and company context.

| Component | Public URL |
|---|---|
| Portal | `https://<PORTAL_HOST>/` |
| Agent 1 | `https://<AGENT1_HOST>/workspace` |
| Agent 2 | `https://<PORTAL_HOST>/agent2/` |
| Agent 3 | `https://<AGENT3_HOST>/` |
| Agent 4 | `https://<PORTAL_HOST>/agent4/` |
| Agent 2 training station | `https://<PORTAL_HOST>/station/` (separate login) |

Agent 1's usable link includes a short-lived Portal connection ticket, and Agent 2 checks the Portal session. Judges should enter through Portal so those two agents receive the right company and session context.

## Before starting

- A Linux VM with Docker Engine and the Compose plugin. The image builds a separate CPU-only Agent 2 HE environment using Concrete; its first build is larger and takes longer than the basic Agent 2 image.
- Three DNS A records pointing to the VM: one for Portal, one for Agent 1, and one for Agent 3.
- In the Azure network security group, allow inbound TCP 80 and 443. Limit SSH (22) to your own IP. Do not open ports 8011, 8040, 8640, 8766, or 8800.
- Provider API credentials for Agent 3 and Agent 4. Their variables are listed in `.env.example`.
- The Agent 4 demo warehouse. `bootstrap-data.sh` copies it (and an Agent 3 legal corpus, if one exists locally) from the current checkout. The Agent 3 legal corpus does not have to be copied: when `state/agent3/legal_corpus.sqlite3` is missing, Agent 3 downloads the core tax documents from vbpl.vn on first start (about 2 minutes, needs outbound HTTPS) and then embeds them with the configured embedding API. A full sync can be started later from Agent 3's legal corpus page. Set `AGENT3_LAW_AUTOBUILD=0` to turn this off.

The repository's current resource note recommends 8 vCPU, 32 GB RAM, and 200 GB SSD for the full workload. A smaller VM may start the interfaces but has not been verified for all analysis paths. The container build also needs outbound access to download Python, Node, CPU PyTorch, and Concrete packages.

## Prepare Agent 2 data without putting it in Git

On the checkout that already has the local Agent 2 demo state, run:

```sh
python deploy/azure-vm/prepare-agent2-state.py
```

On Windows, use `py -3 deploy/azure-vm/prepare-agent2-state.py` if `python` does not select Python 3.

The script creates `deploy/azure-vm/state/agent2` and `state/portal/agent2_access.json` using SQLite's backup API. It copies the access policy and demo databases only; it does not copy HE keys, Portal passwords, or local config. The entire `state/` directory is ignored by Git. Transfer that state directory to the VM with a private file-transfer method before starting Compose. Do not commit it.

When provisioning HE on Linux, save its keys under `/state/agent2/secrets`; the Linux provider creates owner-only files and does not read Windows DPAPI files. Existing DPAPI keys cannot be reused on Linux, so create a fresh synthetic demo context. This file-permission provider is intended for the competition demo only; host root can read it. Use Azure Key Vault for production. The current scaffold does not generate HE circuit bundles or node configs automatically.

## Configure the hostnames and credentials

From the repository root on the VM:

```sh
cd deploy/azure-vm
cp .env.example .env
```

Edit `.env` and replace the three `example.com` names with the DNS names that point to this VM. Set `MAF_UID` and `MAF_GID` to the output of `id -u` and `id -g` for the account running Docker. Add the four Agent 3/4 API keys.

Set the training station login. `STATION_USER` is any name; `STATION_PASSWORD_HASH` is the output of:

```sh
docker run --rm caddy:2-alpine caddy hash-password --plaintext 'choose-a-strong-password'
```

Put the hash in single quotes in `.env` (it contains `$`). Compose refuses to start while either value is missing.

If the database artifacts were not included in the checkout, copy them to the VM before the next step:

```text
deploy/azure-vm/state/demo/warehouse.duckdb
deploy/azure-vm/state/agent3/legal_corpus.sqlite3   (optional: built automatically when missing)
```

Run the bootstrap helper from `deploy/azure-vm`. It copies only those two demo artifacts when present; it does not copy Portal accounts, passwords, agent keys, or local state.

```sh
./bootstrap-data.sh
```

The first run creates the persistent state directories. Keep `state/` and the two Caddy volumes for as long as the demo is live. Do not commit `.env` or `state/`.

## Build and start

```sh
docker compose -f compose.yaml up --build -d
docker compose -f compose.yaml ps
docker compose -f compose.yaml logs -f maf-demo
```

Once Caddy has issued certificates, open `https://<PORTAL_HOST>`. The Portal page includes Agent 1–4. Agent 3 and Agent 4 will remain offline until their API keys are set and both demo data files exist. Agent 2's interactive access also needs the demo access policy and snapshot/model data configured in the persistent state.

The Agent 2 joint training flow works like the local `run_web.bat` setup: each company opens Agent 2 → "Đóng góp huấn luyện", loads its CSV and presses "Mã hóa và gửi lên trạm"; the operator then opens `https://<PORTAL_HOST>/station/`, signs in with the station login and presses "Huấn luyện trên dữ liệu đã mã hóa"; each company finally syncs the accepted model. The station runs inside the app container on port 8890 and is reachable only through Caddy.

Give judges only the Portal URL. They do not need a browser pointed at the VM's ports or your computer turned on. The VM itself must stay running for the public link to work.

## Stop and remove after the competition

```sh
docker compose -f compose.yaml down
```

This stops the containers and leaves the VM, its disk, state folder, and Caddy certificate volumes in place. Delete the Azure VM and its attached resources when the demo is no longer needed to stop compute and disk charges.

## Scope and limits

This is a competition-demo setup, not a production security or availability profile. Agent 2's joint training station uses CKKS (TenSEAL) inside the Agent 2 process and needs no extra worker. Concrete HE workers are opt-in, as in the local setup: they need Linux-generated circuit bundles, key contexts, and worker configs before Portal will start them. Agent 2 also needs its access policy and demo snapshot/model data. Agent 4 currently uses the demo API and the warehouse file provided above.

The app container persists Portal state, Agent 1 state, Agent 2 databases, Agent 3 workspaces, and the Agent 3 legal database under `state/`. Keep a backup before rebuilding or deleting the VM.
