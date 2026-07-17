# Proxmox Multi-Host Setup — Summary & Instructions

Generated: 2026-07-16
Scope: Extending the `proxmox-control` Hermes skill to manage 3 standalone
Proxmox VE servers, each with its own login (no shared cluster).

---

## What changed

The stock skill (`proxmox-control`) only handled a single `PROXMOX_HOST`.
This extension adds multi-host support for standalone servers.

Files added to `~/.hermes/skills/proxmox-control/`:
- `references/proxmox_multi.py`      — multi-host helper (get_client / get_all / list_hosts)
- `references/proxmox-hosts.example.json` — registry template
- `.venv/`                          — venv with proxmoxer 2.3.0 + requests 2.34.2
- `SKILL.md`                         — updated with "Multi-Host (Standalone Servers)" section

---

## How it answers: "can it handle multiple Proxmox servers?"

- Multiple NODES in ONE cluster: YES, stock skill (connect to one node,
  `proxmox.nodes.get()` lists all). No change needed.
- Multiple STANDALONE hosts (your case): now YES via `proxmox_multi.py`.
  Each host = independent `ProxmoxAPI` client built from a registry entry.

---

## Setup (do this once)

1. Create the venv (already done, but repeatable):
   ```bash
   cd ~/.hermes/skills/proxmox-control
   uv venv .venv && uv pip install proxmoxer requests
   ```

2. Write the real registry at `~/.config/proxmox-hosts.json`:
   ```json
   {
     "hosts": {
       "pve1": {
         "host": "192.168.8.10", "port": 8006, "verify_ssl": false,
         "auth": { "type": "token", "user": "root@pam",
                   "token_id": "root@pam!agent",
                   "secret": { "env": "PROXMOX_PVE1_TOKEN_SECRET" } }
       },
       "pve2": {
         "host": "192.168.8.11", "port": 8006, "verify_ssl": false,
         "auth": { "type": "password", "user": "root@pam",
                   "secret": { "env": "PROXMOX_PVE2_PASSWORD" } }
       },
       "pve3": {
         "host": "192.168.8.12", "port": 8006, "verify_ssl": false,
         "auth": { "type": "token", "user": "admin@pve",
                   "token_id": "admin@pve!agent",
                   "secret": { "bwsm": "<BWSM_SECRET_UUID>" } }
       }
     }
   }
   ```
   - Replace IPs with your real hosts.
   - Secrets NEVER stored plaintext. Forms:
     `{ "env": "VAR" }`  |  `{ "bwsm": "<uuid>" }`  |  `{ "value": "..." }` (discouraged)

3. Supply credentials (pick per-host):
   - env:  `export PROXMOX_PVE1_TOKEN_SECRET=...`  (and PVE2_PASSWORD, etc.)
   - BWSM: store token secret as a BWSM secret; put its UUID in `bwsm`;
           ensure `BWS_ACCESS_TOKEN` is exported (`bws` CLI at ~/.local/bin/bws).

4. Smoke test (read-only):
   ```bash
   cd ~/.hermes/skills/proxmox-control
   .venv/bin/python references/proxmox_multi.py --list-hosts
   .venv/bin/python references/proxmox_multi.py --status
   ```

---

## Usage in Python

```python
from proxmox_multi import get_client, get_all, list_hosts

pve1 = get_client("pve1")          # single host ProxmoxAPI
all_clients = get_all()            # {name: ProxmoxAPI | Exception}

for name, px in get_all().items():
    if isinstance(px, Exception):  # one dead host must not abort the batch
        print(f"{name}: build error -> {px}")
        continue
    for n in px.nodes.get():
        print(f"{name}: {n['node']} ({n['status']})")
```

---

## Verified gotchas (real testing, not assumptions)

- proxmoxer PASSWORD auth connects EAGERLY at construction (POSTs
  /access/ticket). TOKEN auth is LAZY. So `get_all()` wraps each build in
  try/except — an unreachable password host returns an Exception in the dict,
  not a hard crash. Test confirmed: pve2 unreachable -> captured cleanly.
- proxmoxer token kwargs are `token_name` (part after `!`) + `token_value`,
  NOT `token_secret`. The helper splits `token_id` for you.
- BWSM resolution requires `BWS_ACCESS_TOKEN` in env and `bws` at
  ~/.local/bin/bws. Test confirmed bwsm path runs (fails cleanly on bad UUID).

---

## Original install note

Stock skill installed from:
`https://raw.githubusercontent.com/danielbitpro/hermes-proxmox-control/master/skills/proxmox-control/SKILL.md`
(owner danielbitpro, repo hermes-proxmox-control, branch master).
`hermes skills install <owner/repo>` FAILED — not in any indexed registry;
direct raw-URL install worked. Security scan: SAFE (2 MEDIUM supply-chain
notes for unpinned `pip install proxmoxer`).
