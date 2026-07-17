#!/usr/bin/env python3
"""
proxmox_multi.py — multi-host Proxmox client helper for the proxmox-control skill.

Supports N *standalone* Proxmox VE hosts, each with its own login, from a single
registry file. Secrets are NEVER stored plaintext in the registry; they are
resolved from environment variables or Bitwarden Secrets Manager (BWSM).

Registry file: ~/.config/proxmox-hosts.json
  {
    "hosts": {
      "pve1": {
        "host": "192.168.8.10",
        "port": 8006,                # optional, default 8006
        "verify_ssl": false,         # optional, default false (LAN)
        "auth": {
          "type": "token",           # "token" | "password"
          "user": "root@pam",
          "token_id": "root@pam!agent",
          "secret": { "env": "PROXMOX_PVE1_TOKEN_SECRET" }
        }
      },
      "pve2": {
        "host": "192.168.8.11",
        "auth": {
          "type": "password",
          "user": "root@pam",
          "secret": { "env": "PROXMOX_PVE2_PASSWORD" }
        }
      },
      "pve3": {
        "host": "192.168.8.12",
        "auth": {
          "type": "token",
          "user": "admin@pve",
          "token_id": "admin@pve!agent",
          "secret": { "bwsm": "<SECRET_UUID>" }
        }
      }
    }
  }

Secret spec forms:
  { "env": "VAR_NAME" }            -> read from environment
  { "bwsm": "<secret-uuid>" }      -> read from Bitwarden Secrets Manager
  { "value": "..." }               -> inline (DISCOURAGED; warns)

Usage:
  from proxmox_multi import get_client, get_all, list_hosts
  pve1 = get_client("pve1")         # one host
  all_clients = get_all()           # every host: {name: ProxmoxAPI}
  for name, px in get_all().items():
      print(name, px.nodes.get())

CLI:
  python proxmox_multi.py --list-hosts   # show hosts (no connection)
  python proxmox_multi.py --status       # connect each, print node summary
"""
import json
import os
import subprocess
import sys
from pathlib import Path

try:
    from proxmoxer import ProxmoxAPI
except ImportError:
    sys.exit("proxmoxer not installed. Run: uv pip install proxmoxer")

DEFAULT_REGISTRY = Path(os.path.expanduser("~")) / ".config" / "proxmox-hosts.json"


def _resolve_bwsm(ref: str) -> str:
    bws = Path(os.path.expanduser("~/.local/bin/bws"))
    exe = str(bws) if bws.exists() else "bws"
    if not os.environ.get("BWS_ACCESS_TOKEN"):
        raise RuntimeError("BWS_ACCESS_TOKEN not set in environment (needed for bwsm secrets)")
    r = subprocess.run([exe, "secret", "get", ref], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"bws get failed for {ref}: {r.stderr.strip()}")
    try:
        return json.loads(r.stdout)["value"]
    except (json.JSONDecodeError, KeyError):
        return r.stdout.strip()


def _resolve_secret(spec) -> str:
    if spec is None:
        raise RuntimeError("missing secret spec")
    if "value" in spec:
        print("[warn] inline secret in registry — prefer env/bwsm", file=sys.stderr)
        return spec["value"]
    if "env" in spec:
        v = os.environ.get(spec["env"])
        if not v:
            raise RuntimeError(f"env var {spec['env']} not set")
        return v
    if "bwsm" in spec:
        return _resolve_bwsm(spec["bwsm"])
    raise RuntimeError(f"unknown secret spec: {spec!r}")


def load_registry(path=None) -> dict:
    p = Path(path or DEFAULT_REGISTRY)
    if not p.exists():
        raise RuntimeError(f"registry not found: {p}")
    return json.loads(p.read_text())


def build_client(name: str, cfg: dict) -> "ProxmoxAPI":
    host = cfg["host"]
    port = cfg.get("port", 8006)
    verify_ssl = cfg.get("verify_ssl", False)
    auth = cfg["auth"]
    if auth["type"] == "token":
        token_id = auth["token_id"]
        # token_id format: user@realm!tokenname  ->  token_name is the part after '!'
        token_name = token_id.split("!", 1)[1] if "!" in token_id else token_id
        return ProxmoxAPI(
            host, port=port, verify_ssl=verify_ssl,
            user=auth["user"],
            token_name=token_name,
            token_value=_resolve_secret(auth["secret"]),
        )
    if auth["type"] == "password":
        return ProxmoxAPI(
            host, port=port, verify_ssl=verify_ssl,
            user=auth["user"],
            password=_resolve_secret(auth["secret"]),
        )
    raise RuntimeError(f"unknown auth type {auth['type']!r} for host {name}")


def get_client(name: str, registry_path=None) -> "ProxmoxAPI":
    reg = load_registry(registry_path)
    if name not in reg.get("hosts", {}):
        raise RuntimeError(f"host {name!r} not in registry. Known: {list(reg.get('hosts', {}))}")
    return build_client(name, reg["hosts"][name])


def get_all(registry_path=None) -> dict:
    """Build a client per host.

    NOTE: proxmoxer's *password* backend connects eagerly at construction
    (it POSTs /access/ticket immediately); the *token* backend is lazy.
    A dead/reachable host with password auth will therefore raise at build
    time. To avoid one bad host aborting the whole call, per-host failures
    are captured as Exception placeholders in the returned dict.

    Returns: {name: ProxmoxAPI | Exception}
    Check `isinstance(v, Exception)` before using a client.
    """
    reg = load_registry(registry_path)
    out = {}
    for name, cfg in reg.get("hosts", {}).items():
        try:
            out[name] = build_client(name, cfg)
        except Exception as e:
            out[name] = e
    return out


def list_hosts(registry_path=None) -> list:
    reg = load_registry(registry_path)
    return list(reg.get("hosts", {}).keys())


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="proxmox multi-host helper")
    ap.add_argument("--list-hosts", action="store_true", help="list host names (no connection)")
    ap.add_argument("--status", action="store_true", help="connect each host, print node summary")
    ap.add_argument("--registry", help="path to hosts registry JSON")
    args = ap.parse_args()

    if args.list_hosts:
        for h in list_hosts(args.registry):
            print(h)
        return
    if args.status:
        for name, px in get_all(args.registry).items():
            if isinstance(px, Exception):
                print(f"{name}: BUILD ERROR -> {px}")
                continue
            try:
                nodes = px.nodes.get()
                print(f"{name}: OK -> " + ", ".join(f"{n['node']}({n['status']})" for n in nodes))
            except Exception as e:
                print(f"{name}: ERROR -> {e}")
        return
    ap.print_help()


if __name__ == "__main__":
    _cli()
