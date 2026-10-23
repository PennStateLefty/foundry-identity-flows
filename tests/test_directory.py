import copy
from contextlib import chdir, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path("scripts") / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


credential = load_script("credential")
with patch.dict("sys.modules", {"credential": credential}):
    permissions = load_script("permissions")


class PermissionDeclarationTests(unittest.TestCase):
    def setUp(self):
        self.apps = {
            "api-object": {
                "id": "api-object", "appId": "api-application", "requiredResourceAccess": [],
                "api": {"oauth2PermissionScopes": [
                    {"id": "api-scope", "value": "access_as_user", "isEnabled": True},
                ]},
            },
            "desktop-object": {
                "id": "desktop-object", "appId": "desktop-application", "requiredResourceAccess": [],
            },
        }
        self.writes = []
        self.fail_on = None
        self.ignore_write = False
        self.show_counts = {}
        self.concurrent_change = False

    def az(self, *args):
        if args == ("account", "show"):
            return {"tenantId": "test-tenant"}
        if args[:3] == ("ad", "sp", "list"):
            return [{"appId": "foundry-resource", "oauth2PermissionScopes": [
                {"id": "foundry-scope", "value": "user_impersonation", "isEnabled": True},
            ]}]
        if args[:3] == ("ad", "app", "show"):
            identifier = args[-1]
            self.show_counts[identifier] = self.show_counts.get(identifier, 0) + 1
            app = copy.deepcopy(self.apps[identifier])
            if self.concurrent_change and self.show_counts[identifier] == 2:
                app["requiredResourceAccess"] = [
                    {"resourceAppId": "unexpected-resource",
                     "resourceAccess": [{"id": "unexpected-scope", "type": "Scope"}]},
                ]
            return app
        if args[:3] == ("rest", "--method", "PATCH"):
            identifier = args[4].rsplit("/", 1)[-1]
            self.writes.append(args)
            if identifier == self.fail_on:
                raise RuntimeError("Simulated interrupted mutation.")
            if not self.ignore_write:
                self.apps[identifier]["requiredResourceAccess"] = json.loads(args[6])["requiredResourceAccess"]
            return None
        self.fail(f"Unexpected Azure command: {args[:3]}")

    def run_main(self, *, apply=True):
        argv = ["permissions.py", "--tenant", "test-tenant"] + (["--apply"] if apply else [])
        with patch("sys.argv", argv), patch.object(permissions, "az", self.az), \
             patch("builtins.input", return_value="DECLARE DELEGATED SCOPES"), redirect_stdout(io.StringIO()):
            permissions.main()

    def local_state(self):
        Path(".local").mkdir()
        Path(".local/tenant-objects.json").write_text(json.dumps({
            "complete": True, "tenant_id": "test-tenant",
            "objects": [{"kind": "api-app", "id": "api-object"},
                        {"kind": "public-app", "id": "desktop-object"}],
        }))

    def test_dry_run_has_no_mutations(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            self.run_main(apply=False)
            self.assertFalse(self.writes)
            self.assertFalse(Path(".local/permission-declarations.json").exists())

    def test_apply_declares_only_three_delegated_scopes(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            self.run_main()
            self.assertEqual(len(self.writes), 2)
            entries = [a for app in self.apps.values() for resource in app["requiredResourceAccess"]
                       for a in resource["resourceAccess"]]
            self.assertEqual(len(entries), 3)
            self.assertTrue(all(a["type"] == "Scope" for a in entries))
            state = Path(".local/permission-declarations.json")
            self.assertEqual(json.loads(state.read_text())["status"], "complete")
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_existing_state_prevents_repeating_writes(self):
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            self.run_main()
            with self.assertRaisesRegex(RuntimeError, "state exists"):
                self.run_main()
            self.assertEqual(len(self.writes), 2)

    def test_unexpected_permissions_are_preserved(self):
        self.apps["api-object"]["requiredResourceAccess"] = [
            {"resourceAppId": "unexpected-resource",
             "resourceAccess": [{"id": "unexpected-application-role", "type": "Role"}]},
        ]
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            with self.assertRaisesRegex(ValueError, "Unexpected permission"):
                self.run_main()
            self.assertFalse(self.writes)

    def test_concurrent_change_stops_before_mutation(self):
        self.concurrent_change = True
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            with self.assertRaisesRegex(RuntimeError, "changed during approval"):
                self.run_main()
            self.assertFalse(self.writes)

    def test_read_back_failure_does_not_record_completion(self):
        self.ignore_write = True
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                self.run_main()
            state = json.loads(Path(".local/permission-declarations.json").read_text())
            self.assertEqual(state["completed"], [])
            self.assertEqual(state["status"], "pending")

    def test_partial_failure_is_not_retried(self):
        self.fail_on = "desktop-object"
        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            self.local_state()
            with self.assertRaisesRegex(RuntimeError, "Simulated interrupted"):
                self.run_main()
            state = json.loads(Path(".local/permission-declarations.json").read_text())
            self.assertEqual(state["completed"], ["api-app"])
            self.assertEqual(state["current"], "public-app")
            with self.assertRaisesRegex(RuntimeError, "state exists"):
                self.run_main()
            self.assertEqual(len(self.writes), 2)

    def test_cli_accepts_empty_patch_response(self):
        with patch.object(credential.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = ""
            self.assertIsNone(credential.az("rest", "--method", "PATCH"))


if __name__ == "__main__":
    unittest.main()
