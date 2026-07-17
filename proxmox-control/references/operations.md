# Proxmox Operations

Load this reference only after identifying the target host and guest. Before any state-changing call, confirm the requested operation with the user, check current status, and create a snapshot when rollback is appropriate.

## Connect and resolve the node

```python
from proxmoxer import ProxmoxAPI

proxmox = ProxmoxAPI(
    host,
    port=8006,
    user=user,
    token_name=token_name,
    token_value=token_value,
    verify_ssl=True,
)
nodes = proxmox.nodes.get()
node_name = nodes[0]["node"]
node = proxmox.nodes(node_name)
```

Never assume a node is named `pve`.

## Inspect guests

```python
for vm in node.qemu.get():
    print(f"VM {vm['vmid']}: {vm['name']} ({vm['status']})")

for container in node.lxc.get():
    print(f"CT {container['vmid']}: {container['name']} ({container['status']})")
```

For a selected QEMU guest:

```python
status = node.qemu(vm_id).status.current.get()
config = node.qemu(vm_id).config.get()
```

For a selected LXC guest, use `node.lxc(ct_id)` in the same pattern.

## Power operations

Confirm the target guest and its current state before submitting any of these calls.

```python
# QEMU VM
upid = node.qemu(vm_id).status.start.post()
upid = node.qemu(vm_id).status.shutdown.post()
upid = node.qemu(vm_id).status.stop.post()
upid = node.qemu(vm_id).status.reboot.post()

# LXC container
upid = node.lxc(ct_id).status.start.post()
upid = node.lxc(ct_id).status.shutdown.post()
upid = node.lxc(ct_id).status.stop.post()
upid = node.lxc(ct_id).status.reboot.post()
```

`stop` is a hard power operation. Prefer `shutdown` when the guest is responsive.

### Track an asynchronous task

State-changing Proxmox calls return a UPID. Keep that value and check the task endpoint rather than attempting to derive it from an earlier status response.

```python
import time

while True:
    task = node.tasks(upid).status.get()
    if task.get("status") == "stopped":
        break
    time.sleep(1)
```

Inspect `task["exitstatus"]` before reporting success.

## Snapshots

```python
node.qemu(vm_id).snapshot.post(snapshot="pre_update")

for snapshot in node.qemu(vm_id).snapshot.get():
    print(snapshot["name"])

node.qemu(vm_id).snapshot("snapshot_name").rollback.post()
node.qemu(vm_id).snapshot("old_snapshot").delete()
```

Snapshot rollback and deletion are destructive. Confirm the exact snapshot name and guest before proceeding.

## Resource and storage inspection

```python
for resource in node.resources.get():
    print(resource["type"], resource["id"])

for storage in node.storage.get():
    print(storage["storage"], storage.get("avail"), storage.get("total"))
```

## Clone a QEMU VM or template

Use the source guest's QEMU resource. `unprivileged` is an LXC setting and does not apply to a QEMU clone.

```python
upid = node.qemu(template_id).clone.post(
    newid=new_vm_id,
    name="new-vm-name",
    storage="local-zfs",
)
```

Confirm source, destination VM ID, storage target, and whether a full or linked clone is intended before cloning.

## Convert a QEMU VM to a template

```python
upid = node.qemu(vm_id).template.post()
```

This changes how the guest is managed. Confirm it is the intended source before proceeding.

## API references

- [Proxmox VE `qm` command reference](https://pve.proxmox.com/pve-docs/qm.1.html)
- [Proxmox VE API viewer](https://pve.proxmox.com/pve-docs/api-viewer/)
- [proxmoxer README](https://github.com/proxmoxer/proxmoxer)
