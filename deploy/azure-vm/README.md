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

Agent 1's usable link includes a short-lived Portal connection ticket, and Agent 2 checks the Portal session. Judges should enter through Portal so those two agents receive the right company and session context.

## Before starting

- A Linux VM with Docker Engine and the Compose plugin.
- Three DNS A records pointing to the VM: one for Portal, one for Agent 1, and one for Agent 3.
- In the Azure network security group, allow inbound TCP 80 and 443. Limit SSH (22) to your own IP. Do not open ports 8011, 8040, 8640, 8766, or 8800.
- Provider API credentials for Agent 3 and Agent 4. Their variables are listed in `.env.example`.
- The Agent 4 demo warehouse and Agent 3 legal corpus. `bootstrap-data.sh` copies them from the current checkout when those local artifacts are present.

The repository's current resource note recommends 8 vCPU, 32 GB RAM, and 200 GB SSD for the full workload. A smaller VM may start the interfaces but has not been verified for all analysis paths. The container build also needs outbound access to download Python and Node packages.

## Configure the hostnames and credentials

From the repository root on the VM:

```sh
cd deploy/azure-vm
cp .env.example .env
```

Edit `.env` and replace the three `example.com` names with the DNS names that point to this VM. Set `MAF_UID` and `MAF_GID` to the output of `id -u` and `id -g` for the account running Docker. Add the four Agent 3/4 API keys.

If the database artifacts were not included in the checkout, copy them to the VM before the next step:

```text
deploy/azure-vm/state/demo/warehouse.duckdb
deploy/azure-vm/state/agent3/legal_corpus.sqlite3
```

Run the bootstrap helper from `deploy/azure-vm`. It copies only those two demo artifacts; it does not copy Portal accounts, passwords, agent keys, or local state.

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

Give judges only the Portal URL. They do not need a browser pointed at the VM's ports or your computer turned on. The VM itself must stay running for the public link to work.

## Stop and remove after the competition

```sh
docker compose -f compose.yaml down
```

This stops the containers and leaves the VM, its disk, state folder, and Caddy certificate volumes in place. Delete the Azure VM and its attached resources when the demo is no longer needed to stop compute and disk charges.

## Scope and limits

This is a competition-demo setup, not a production security or availability profile. It does not configure Agent 2's optional encrypted HE worker; that remains a separate Linux setup with its own keys and runtime bundle. Agent 2 also needs its access policy and demo snapshot/model data. Agent 4 currently uses the demo API and the warehouse file provided above.

The app container persists Portal state, Agent 1 state, Agent 2 databases, Agent 3 workspaces, and the Agent 3 legal database under `state/`. Keep a backup before rebuilding or deleting the VM.
