"""Create one explicitly approved, short-lived credential for the lab API."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess


def az(*args):
    result = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Azure operation failed; inspect local state before any further write.")
    return json.loads(result.stdout) if result.stdout.strip() else None


def save(path: Path, value: dict, *, exclusive: bool = False):
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(value, output, indent=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    directory = Path(".local")
    if directory.is_symlink():
        raise ValueError("Local credential storage must not be a symbolic link.")
    manifest = json.loads((directory / "tenant-objects.json").read_text())
    if not manifest["complete"] or manifest["tenant_id"] != args.tenant:
        raise ValueError("The completed bootstrap manifest must match the approved tenant.")
    apps = [item for item in manifest["objects"] if item["kind"] == "api-app"]
    if len(apps) != 1:
        raise ValueError("Exactly one API registration must be recorded.")
    app = apps[0]
    if az("account", "show")["tenantId"] != args.tenant:
        raise ValueError("Active tenant does not match the approved tenant.")
    print("Plan: add one 24-hour credential to the recorded API registration; replace no existing credentials.")
    if not args.apply:
        return
    state = directory / "api-credential-state.json"
    secret = directory / "api-credential.json"
    if state.exists() or secret.exists():
        raise RuntimeError("Credential state already exists; do not automatically repeat a credential request.")
    if input("Type CREATE 24H CREDENTIAL to approve this one credential: ") != "CREATE 24H CREDENTIAL":
        raise RuntimeError("Approval not provided.")
    expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    request = {"application_id": app["appId"], "status": "pending", "expires_at": expires}
    save(state, request, exclusive=True)
    result = az(
        "rest", "--method", "POST",
        "--url", f"https://graph.microsoft.com/v1.0/applications/{app['id']}/addPassword",
        "--body", json.dumps({"passwordCredential": {
            "displayName": "identity-lab-24h", "endDateTime": expires,
        }}),
    )
    save(secret, {
        "tenant_id": args.tenant, "client_id": app["appId"],
        "client_secret": result["secretText"], "key_id": result["keyId"], "expires_at": expires,
    }, exclusive=True)
    save(state, {**request, "status": "complete", "key_id": result["keyId"]})
    print("Credential created and stored locally with owner-only access. Its value was not printed.")


if __name__ == "__main__":
    main()
