---
name: proxmox-control
description: Control Proxmox VE hypervisors via the REST API — VM/container status, power management, snapshots, resource monitoring, storage, and template cloning. Use when managing one or more standalone Proxmox VE servers or a Proxmox cluster (list/start/stop VMs, take snapshots, check node health, clone templates).
license: MIT
category: devops
---

# Proxmox VE Control

Control a Proxmox VE hypervisor via the REST API using the `proxmoxer` Python library. Covers VM/container status, power management, snapshots, resource monitoring, storage, and template operations.

## Installation

Install the `proxmoxer` library into your Python environment:

```bash
pip install proxmoxer requests
```

> This skill's multi-host helper uses a venv. Set one up once:
> ```bash
> cd ~/.hermes/skills/proxmox-control
> uv venv .venv && uv pip install proxmoxer requests
> ```

## Multi-Host (Standalone Servers)

The patterns above assume a single `PROXMOX_HOST`. For **N standalone Proxmox
servers, each with its own login**, use the bundled helper `references/proxmox_multi.py`
and a host registry JSON (`~/.config/proxmox-hosts.json`).

### Registry format

Secrets are NEVER stored plaintext. Resolve them from env vars or Bitwarden
Secrets Manager (BWSM):

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

Secret spec forms: `{ "env": "VAR" }`, `{ "bwsm": "<uuid>" }`, or
`{ "value": "..." }` (discouraged — warns). See
`references/proxmox-hosts.example.json`.

### Using the helper

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

CLI smoke test (no VM changes):

```bash
cd ~/.hermes/skills/proxmox-control
.venv/bin/python references/proxmox_multi.py --list-hosts
.venv/bin/python references/proxmox_multi.py --status
```

### Gotchas (verified)

- **proxmoxer password auth connects at construction** (POSTs
  `/access/ticket`). Token auth is lazy. So `get_all()` wraps each build in
  try/except — an unreachable *password* host returns an `Exception` in the
  dict, not a hard crash.
- **Token kwargs**: proxmoxer wants `token_name` (the part after `!`) +
  `token_value`, NOT `token_secret`. The helper splits `token_id` for you.
- **BWSM**: `BWS_ACCESS_TOKEN` must be set in the environment for `bwsm`
  secret resolution (the `bws` CLI is at `~/.local/bin/bws`).

## Authentication

Proxmox auth is configured via environment variables. Set them in your `.env` file or export them directly.

### Option A: Token-Based (Recommended for Production)

```bash
PROXMOX_HOST=192.168.1.100
PROXMOX_PORT=8006
PROXMOX_TOKEN_ID=youruserid!tokenid
PROXMOX_TOKEN_SECRET=<your-secret>
```

### Option B: Username/Password (Simpler, Good for LAN)

```bash
PROXMOX_HOST=192.168.1.100
PROXMOX_PORT=8006
PROXMOX_USER=youruser@pve
PROXMOX_PASSWORD=yourpassword
```

### Creating a Proxmox API Token (one-time setup)

Run these commands on the Proxmox host:

```bash
# Create a token (replace YOURUSER with your actual username)
pvesh create /access/tokens -userid YOURUSER@pve -privsep 0 -description "Agent"

# Or create a token for root:
pvesh create /access/tokens -userid root@pam -privsep 0 -description "Agent"
```

**Important:** The token ID will look like `root@pam!agent` (format: `user@realm!token_name`). Copy the secret immediately — it won't be shown again.

### Realm Suffix Matters

Proxmox has multiple realms (`pam`, `pve`, etc.). `root@pam` and `root@pve` are different authentication domains. If one realm fails with 401, try the other. Check available realms with `pveum user list` on the Proxmox host.

## Core Patterns

### Base Connection Template

```python
# Set these as environment variables before running:
#   export PROXMOX_HOST="192.168.1.100"
#   export PROXMOX_USER="youruser@pve"
#   export PROXMOX_PASSWORD="yourpassword"
# Or use a .env file with python-dotenv

from proxmoxer import ProxmoxAPI

host = "192.168.1.100"
port = 8006
verify_ssl = False  # Use True with proper CA cert for production

proxmox = ProxmoxAPI(
    host, port=port,
    user="youruser@pve",
    password="yourpassword",
    verify_ssl=verify_ssl
)
```

> **Security note:** Never hardcode credentials in production code. Use environment variables, a `.env` file with `python-dotenv`, or a secrets manager. The example above uses placeholder values for documentation purposes only.

### Discover Node Names Dynamically

**Never hardcode the node name.** Proxmox clusters may use custom names (`prox`, `pve`, `proxmox1`, etc.):

```python
nodes = proxmox.nodes.get()
for node in nodes:
    print(f"Node: {node['node']} ({node['status']})")

node_name = nodes[0]['node']  # Use this variable everywhere
```

## VM Management

### List VMs and Containers

```python
# List all VMs (QEMU)
node = proxmox.nodes(node_name)
vms = node.qemu.get()
for vm in vms:
    print(f"VM {vm['vmid']:4d} | {vm['name']:<25s} | {vm['status']} | CPU: {vm['cpus']} | RAM: {vm['maxmem']//1024//1024}MB")

# List all containers (LXC)
ctrs = node.lxc.get()
for ct in ctrs:
    print(f"CT {ct['vmid']:4d} | {ct['name']:<25s} | {ct['status']}")
```

### Get VM Status and Config

```python
# Current status
status = node.qemu(vm_id).status.current.get()
print(f"CPU: {status.get('cpu', 0):.2f}%, MEM: {status.get('maxmem', 0)//1024//1024}MB")

# Configuration
config = node.qemu(vm_id).config.get()
print(f"Disks: {config.get('scsi0', 'N/A')}, Boot: {config.get('boot', 'N/A')}")
```

### Power Management

```python
# Start a VM
node.qemu(vm_id).status.current.post(starttime=0)

# Graceful shutdown (send ACPI signal)
node.qemu(vm_id).status.shutdown.post(forcestop=0)

# Hard poweroff
node.qemu(vm_id).status.stop.post()

# Reboot
node.qemu(vm_id).status.reboot.post(forcestop=0)

# Wait for task completion
import time
task_id = status.get('upid', '').split(':')[1]
while True:
    task = node.tasks(task_id).status.get()
    if task.get('status') == 'stopped':
        break
    time.sleep(1)
```

## LXC Container Management

### Get Container Status and Config

```python
# Current status
status = node.lxc(ct_id).status.current.get()
print(f"State: {status['status']}, CPU: {status.get('cpu', 0):.2f}%")

# Configuration
config = node.lxc(ct_id).config.get()
print(f"Template: {config.get('template', False)}, Unprivileged: {config.get('unprivileged', False)}")
```

### Power Management

```python
# Start a container
node.lxc(ct_id).status.start.post()

# Graceful shutdown (send ACPI signal) — NO forcestop param
node.lxc(ct_id).status.shutdown.post()

# Force stop (hard poweroff) — forcestop param here
node.lxc(ct_id).status.stop.post(forcestop=1)

# Reboot
node.lxc(ct_id).status.reboot.post(forcestop=0)

# Check status after operation
import time
for i in range(30):
    time.sleep(2)
    status = node.lxc(ct_id).status.current.get()
    if status['status'] == 'stopped':
        print(f"Container stopped")
        break
    if i >= 14:
        print(f"Timeout — container may still be stopping")
```

> **⚠️ LXC Shutdown Gotcha:** The `forcestop` parameter is **not valid** for `lxc().status.shutdown.post()`. It only works on `lxc().status.stop.post()`. Passing it to shutdown.post() returns `400 Bad Request: property is not defined in schema`.

> **⚠️ Graceful Shutdown Timeout:** LXC containers rely on ACPI signals inside the container. If the container has no guest agent or processes don't respond to ACPI, shutdown may hang indefinitely. Consider using `stop.post(forcestop=1)` after ~60s if `shutdown.post()` doesn't complete.

## Snapshots

```python
# Create a snapshot
node.qemu(vm_id).snapshot.post(snapshot='pre_update')

# List snapshots
for snap in node.qemu(vm_id).snapshot.get():
    print(f"{snap['name']} — {snap['ctime']}")

# Revert to snapshot
node.qemu(vm_id).snapshot('snapshot_name').rollback.post()

# Delete snapshot
node.qemu(vm_id).snapshot('old_snapshot').delete.post()

# Delete all snapshots older than N days (example)
import datetime
cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
for snap in node.qemu(vm_id).snapshot.get():
    snap_time = datetime.datetime.fromtimestamp(snap['ctime'])
    if snap_time < cutoff:
        node.qemu(vm_id).snapshot(snap['name']).delete.post()
```

## Resource Monitoring

```python
# Node-level resources
resources = proxmox.nodes(node_name).resources.get()
for res in resources:
    print(f"{res['type']} {res['id']}: CPU={res.get('cpu',0):.2f}, "
          f"MEM={res.get('memory',0)/1024/1024:.0f}MB, "
          f"DISK={res.get('disk',0)/1024/1024:.0f}MB")

# Individual VM metrics (only for running VMs)
for vm in node.qemu.get():
    if vm['status'] == 'running':
        cur = node.qemu(vm['vmid']).status.current.get()
        print(f"{vm['name']}: CPU={cur.get('cpu',0):.2f}%, "
              f"RAM={cur.get('maxmem',0)/1024/1024:.0f}MB, "
              f"Disk R/W={cur.get('diskread',0)//1024}KB/{cur.get('diskwrite',0)//1024}KB")
```

## Storage Management

```python
# List all storage
for store in proxmox.storage.get():
    print(f"{store['storage']:20s} type={store['type']:10s} "
          f"avail={store.get('avail',0)/1024/1024:.0f}MB / "
          f"total={store.get('total',0)/1024/1024:.0f}MB")

# Add disk to VM
node.qemu(vm_id).config.post(
    virtio='/local-zfs:vm-{vm_id}-disk-1,size=20G'
)
```

## Template & Cloning

```python
# Clone a template to a new VM
node.clone.post(
    sourceid=template_id,
    newid=new_vm_id,
    name='new-vm-name',
    storage='local-zfs',
    unprivileged=1  # Set to 0 for privileged container
)

# Convert VM to template
node.qemu(vm_id).config.post(template=1)

# Convert template back to VM
node.qemu(vm_id).config.post(template=0, vmid=None)
```

## Error Handling

```python
from proxmoxer import ProxmoxWebAPIError, ProxmoxAPIError

try:
    proxmox.nodes(node_name).qemu(vm_id).status.current.get()
except ProxmoxWebAPIError as e:
    print(f"Web/API error: {e}")
except ProxmoxAPIError as e:
    print(f"Proxmox error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Safety Rules

1. **NEVER shutdown, stop, or reboot a VM without confirming with the user first**
2. **Always check VM status before performing power operations**
3. **Prefer graceful shutdown (`shutdown.post`) over hard stop (`stop.post`)**
4. **Create a snapshot before any risky or irreversible operation**
5. **Monitor task completion after power operations** — don't assume instant success
6. **Don't modify LXC containers unless explicitly requested**
7. **Warn before deleting snapshots or VMs**

## Troubleshooting & Pitfalls

| Problem | Cause & Fix |
|---------|-------------|
| **Token secret "regenerates"** | Editing a token in the Proxmox UI generates a new secret. The token ID stays the same, but the secret is different. Always copy the new secret after editing. |
| **401 Unauthorized (realm)** | Wrong realm suffix (`@pam` vs `@pve`). `user@pam` and `user@pve` are different auth domains. Try the other. Run `pveum user list` to see which realms exist. |
| **401 (token exists but fails)** | Token's user has no role assigned. Fix: `pveum user roleadd user@realm / -role PVEAdmin` or `pveum aclmod / -u user@realm -role PVEAdmin` |
| **401 (token auth, password works)** | Token auth may fail even with correct ID + secret. Switch to username/password auth as a fallback — it often works when token auth has permission issues. |
| **595 Unauthorized** | User/token lacks permissions for the requested resource. Check ACLs in Proxmox UI. |
| **Node name errors** | Never hardcode `'pve'`. Always discover via `proxmox.nodes.get()` — your cluster may use `prox`, `pve01`, etc. |
| **SSL verification failed** | Set `verify_ssl=False` for internal LAN. For production, install the Proxmox CA cert and set `verify_ssl=True`. |
| **Connection refused** | Check `PROXMOX_HOST` and `PROXMOX_PORT`. Ensure the host is reachable on the network. |
| **Token secret "regenerates"** | Editing a token in the Proxmox UI generates a new secret. The token ID stays the same, but the secret is different. Always copy the new secret after editing. |
| **Task ID parsing** | `proxmoxer` handles task tracking. After an operation, the response includes an `upid` field. Extract the task ID from `upid.split(':')[1]`. |

## Environment Variables Reference

| Variable | Required | Example | Description |
|----------|----------|---------|-------------|
| `PROXMOX_HOST` | Yes | `192.168.1.100` | Proxmox hypervisor hostname or IP |
| `PROXMOX_PORT` | No | `8006` | API port (default: 8006) |
| `PROXMOX_USER` | Auth B | `root@pve` | Username with realm suffix |
| `PROXMOX_PASSWORD` | Auth B | `yourpassword` | Account password |
| `PROXMOX_TOKEN_ID` | Auth A | `root@pam!agent` | API token ID |
| `PROXMOX_TOKEN_SECRET` | Auth A | `uuid-here` | API token secret |

> **Auth A** = token-based, **Auth B** = username/password. Use one or the other.

## Dependencies

- `proxmoxer` (Python library): `pip install proxmoxer`
- Python 3.7+
- Network access to Proxmox host on port 8006 (HTTPS)