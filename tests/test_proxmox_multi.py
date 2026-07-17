import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT = next(
    path
    for path in (
        ROOT / "proxmox-control" / "scripts" / "proxmox_multi.py",
        ROOT / "proxmox-control" / "references" / "proxmox_multi.py",
    )
    if path.is_file()
)


def load_helper(fake_client):
    fake_proxmoxer = types.ModuleType("proxmoxer")
    setattr(fake_proxmoxer, "ProxmoxAPI", fake_client)
    with patch.dict(sys.modules, {"proxmoxer": fake_proxmoxer}):
        spec = importlib.util.spec_from_file_location("proxmox_multi_under_test", SCRIPT)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load helper from {SCRIPT}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class FakeClient:
    calls = []

    def __init__(self, host, **kwargs):
        self.host = host
        self.kwargs = kwargs
        self.calls.append((host, kwargs))


class ProxmoxMultiTests(unittest.TestCase):
    def setUp(self):
        FakeClient.calls = []
        self.helper = load_helper(FakeClient)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.registry_path = Path(self.temp_dir.name) / "hosts.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_registry(self, hosts):
        self.registry_path.write_text(json.dumps({"hosts": hosts}))

    def test_get_client_splits_token_id_and_resolves_environment_secret(self):
        self.write_registry(
            {
                "pve1": {
                    "host": "pve1.example.test",
                    "auth": {
                        "type": "token",
                        "user": "root@pam",
                        "token_id": "root@pam!agent",
                        "secret": {"env": "PROXMOX_TEST_TOKEN"},
                    },
                }
            }
        )

        with patch.dict(os.environ, {"PROXMOX_TEST_TOKEN": "token-value"}, clear=False):
            client = self.helper.get_client("pve1", self.registry_path)

        self.assertEqual(client.host, "pve1.example.test")
        self.assertEqual(
            FakeClient.calls,
            [
                (
                    "pve1.example.test",
                    {
                        "port": 8006,
                        "verify_ssl": False,
                        "user": "root@pam",
                        "token_name": "agent",
                        "token_value": "token-value",
                    },
                )
            ],
        )

    def test_get_all_keeps_working_hosts_when_one_configuration_is_invalid(self):
        self.write_registry(
            {
                "good": {
                    "host": "good.example.test",
                    "auth": {
                        "type": "password",
                        "user": "root@pam",
                        "secret": {"env": "PROXMOX_TEST_PASSWORD"},
                    },
                },
                "bad": {"host": "bad.example.test", "auth": {"type": "unsupported"}},
            }
        )

        with patch.dict(os.environ, {"PROXMOX_TEST_PASSWORD": "password"}, clear=False):
            clients = self.helper.get_all(self.registry_path)

        self.assertIsInstance(clients["good"], FakeClient)
        self.assertIsInstance(clients["bad"], Exception)


if __name__ == "__main__":
    unittest.main()
