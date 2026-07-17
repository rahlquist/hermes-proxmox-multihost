# hermes-proxmox-multihost

A **Hermes Agent skill** for controlling **multiple standalone Proxmox VE servers**
from one place — each with its own login.

Built on top of [danielbitpro/hermes-proxmox-control](https://github.com/danielbitpro/hermes-proxmox-control),
extended to manage N independent Proxmox hosts (not just one cluster) via a host
registry + a small multi-host helper.

## What it does

- Manage **3+ standalone Proxmox VE servers**, each with separate credentials
- VM/CT list, status, config, power management (start/shutdown/stop/reboot)
- Snapshots (create / list / rollback / delete)
- Resource monitoring (per-node and per-VM CPU/mem/disk)
- Storage management
- Template cloning / convert-to-template
- Fan out any operation across all hosts, with per-host fault tolerance
  (one dead host does not abort the batch)

> One Proxmox **cluster** (many nodes) is also covered — connect to any node and
> `proxmox.nodes.get()` enumerates the rest.

## Install into Hermes

```bash
hermes skills install \
  https://raw.githubusercontent.com/rahlquist/hermes-proxmox-multihost/main/proxmox-control/SKILL.md \
  --yes
```

Or clone and drop `SKILL.md` + `references/` into your profile's skills dir
(`~/.hermes/skills/proxmox-control/`).

## Setup

1. Create a venv with the dependency (`proxmoxer` needs a backend; `requests`):
   ```bash
   cd ~/.hermes/skills/proxmox-control
   uv venv .venv && uv pip install proxmoxer requests
   ```

2. Write the host registry at `~/.config/proxmox-hosts.json` (see
   `references/proxmox-hosts.example.json`). Secrets are **never** stored
   plaintext — resolve them from env vars or Bitwarden Secrets Manager:
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
       }
     }
   }
   ```
   Secret forms: `{ "env": "VAR" }` | `{ "bwsm": "<uuid>" }` | `{ "value": "..." }` (discouraged).

3. Supply credentials:
   - env: `export PROXMOX_PVE1_TOKEN_SECRET=...`
   - BWSM: store the secret in BWSM, put its UUID in `"bwsm"`, and ensure
     `BWS_ACCESS_TOKEN` is exported (`bws` CLI at `~/.local/bin/bws`).

4. Smoke test (read-only):
   ```bash
   cd ~/.hermes/skills/proxmox-control
   .venv/bin/python references/proxmox_multi.py --list-hosts
   .venv/bin/python references/proxmox_multi.py --status
   ```

## Usage

```python
from proxmox_multi import get_client, get_all

pve1 = get_client("pve1")          # single host ProxmoxAPI
for name, px in get_all().items():
    if isinstance(px, Exception):  # one dead host must not abort the batch
        print(f"{name}: build error -> {px}")
        continue
    for n in px.nodes.get():
        print(f"{name}: {n['node']} ({n['status']})")
```

Run from inside `~/.hermes/skills/proxmox-control` (or set
`PYTHONPATH=references`) so `proxmox_multi` is importable.

## Verified gotchas

- **proxmoxer password auth connects eagerly at construction** (POSTs
  `/access/ticket`); token auth is lazy. `get_all()` wraps each build in
  try/except so an unreachable password host returns an `Exception`, not a crash.
- proxmoxer token kwargs are `token_name` (the part after `!`) + `token_value`,
  not `token_secret`. The helper splits `token_id` for you.
- BWSM resolution requires `BWS_ACCESS_TOKEN` in the environment and the
  `bws` CLI available.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill definition (Hermes loads this) |
| `references/proxmox_multi.py` | Multi-host helper (`get_client` / `get_all` / `list_hosts`) |
| `references/proxmox-hosts.example.json` | Registry template |
| `references/proxmoxer-gotchas.md` | Verified proxmoxer behavior and troubleshooting |
| `references/operations.md` | Confirmed guest operation recipes and safety checks |
| `MULTI_HOST_SETUP.md` | Full setup summary & instructions |

## Credits

- **Daniel** ([danielbitpro](https://github.com/danielbitpro/)) — thank you for
  the original Proxmox skill ([hermes-proxmox-control](https://github.com/danielbitpro/hermes-proxmox-control)),
  which this multi-host extension is built on top of.
- **Magnus** ([magnus919](https://github.com/magnus919/)) — thank you for
  [hermes-SkillOpt](https://github.com/magnus919/hermes-SkillOpt) (the optimization
  methodology used to verify and harden this skill's docs) and for the `de-spin`
  skill (used to de-spin the factual claims about `proxmoxer` behavior).
- Multi-host extension added by rahlquist.
