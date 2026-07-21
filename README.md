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
   plaintext.

   **Recommended: Bitwarden Secrets Manager (BWSM).** Hermes sessions do not
   reliably inherit your shell exports, so `env`-var secrets silently fail in
   fresh sessions. BWSM secrets resolve on every call as long as
   `BWS_ACCESS_TOKEN` is set in the Hermes environment.

   ```json
   {
     "hosts": {
       "pve1": {
         "host": "192.168.8.10", "port": 8006, "verify_ssl": false,
         "auth": { "type": "password", "user": "root@pam",
                   "secret": { "bwsm": "89fcfbcf-a30d-..." } }
       },
       "pve2": {
         "host": "192.168.8.11", "port": 8006, "verify_ssl": false,
         "auth": { "type": "token", "user": "root@pam",
                   "token_id": "root@pam!agent",
                   "secret": { "bwsm": "5c916de8-1ff5-..." } }
       }
     }
   }
   ```
   Secret forms: `{ "bwsm": "<uuid>" }` (recommended) | `{ "env": "VAR" }` |
   `{ "value": "..." }` (discouraged — prints a warning).

   `chmod 600 ~/.config/proxmox-hosts.json` — the registry maps hostnames to
   secret UUIDs; treat it as sensitive.

3. Put each password/token into BWSM and get its UUID:
   ```bash
   bws project list                          # find your project id
   bws secret list <PROJECT_ID>              # list secrets, note each `id`
   ```
   Copy each secret's `id` (UUID) into the matching host's `"bwsm"` field.
   **Pitfall:** `bws secret get` takes the UUID, not the key name.

   If you really want env vars instead: `export PROXMOX_PVE1_PASSWORD=...` in
   the same shell that runs the helper — and re-export in every new session.

4. Smoke test (read-only):
   ```bash
   cd ~/.hermes/skills/proxmox-control
   .venv/bin/python scripts/proxmox_multi.py --list-hosts
   .venv/bin/python scripts/proxmox_multi.py --status
   ```

   Expected:
   ```
   pve1: OK -> home(online)
   pve2: OK -> thicc(online)
   ```

## Troubleshooting the smoke test

| Output | Meaning | Fix |
|---|---|---|
| `BUILD ERROR -> env var X not set` | Host uses `{ "env": "X" }` and the var isn't exported | Switch to `{ "bwsm": "<uuid>" }`, or `export X=...` in this shell |
| `BUILD ERROR -> BWS_ACCESS_TOKEN not set` | Helper can't reach BWSM | `export BWS_ACCESS_TOKEN=...` (recover from `~/.hermes/state-snapshots/*/.env`) |
| `BUILD ERROR -> bws get failed for <uuid>` | Wrong UUID or no access | Re-run `bws secret list <PROJECT_ID>` and copy the `id` field |
| `BUILD ERROR -> HTTPSConnection...refused` | Host unreachable / wrong IP or port | `ping <host>`; check the IP is reachable **from the agent host**, not just your client |
| `ERROR -> 401 Unauthorized` | Connected but auth rejected | Wrong realm (`@pam` vs `@pve`), or token user has no role. See SKILL.md troubleshooting table |
| `ERROR -> 595 ... permission` | Auth OK, no rights on resource | Grant ACL: `pveum aclmod / -u <user@realm> -role PVEAdmin` |

## Next steps after a green smoke test

- **Use it in a Hermes session.** Just ask: *"list VMs on pve2"* or *"status of
  all my proxmox hosts"*. The agent loads this skill and calls the helper.
- **Use it from your own Python:**
  ```python
  import sys; sys.path.insert(0, "~/.hermes/skills/proxmox-control/scripts")
  from proxmox_multi import get_client, get_all

  pve2 = get_client("pve2")
  for node in pve2.nodes.get():
      for vm in pve2.nodes(node["node"]).qemu.get():
          print(vm["vmid"], vm["name"], vm["status"])
  ```
- **Add a host:** append a new block under `"hosts"` in the registry, store the
  secret in BWSM, reference its UUID. No other changes needed.
- **Rotate a secret:** create a new secret in BWSM (or rotate the password on
  the Proxmox host), update the UUID in the registry. The old UUID can be
  deleted from BWSM after the smoke test passes.
- **State-changing operations** (start/stop/snapshot/clone) are gated behind
  `references/operations.md` — read it before calling power ops, and always
  confirm with the user first.

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
`PYTHONPATH=scripts`) so `proxmox_multi` is importable.

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
| `scripts/proxmox_multi.py` | Multi-host helper (`get_client` / `get_all` / `list_hosts`) |
| `references/proxmox-hosts.example.json` | Registry template |
| `references/proxmoxer-gotchas.md` | Verified proxmoxer behavior and troubleshooting |
| `references/operations.md` | Confirmed guest operation recipes and safety checks |

## Credits

- **Daniel** ([danielbitpro](https://github.com/danielbitpro/)) — thank you for
  the original Proxmox skill ([hermes-proxmox-control](https://github.com/danielbitpro/hermes-proxmox-control)),
  which this multi-host extension is built on top of.
- **Magnus** ([magnus919](https://github.com/magnus919/)) — thank you for
  [hermes-SkillOpt](https://github.com/magnus919/hermes-SkillOpt) (the optimization
  methodology used to verify and harden this skill's docs) and for the `de-spin`
  skill (used to de-spin the factual claims about `proxmoxer` behavior).
- Multi-host extension added by rahlquist.
