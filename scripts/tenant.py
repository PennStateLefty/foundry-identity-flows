"""Explicit tenant bootstrap; no deletion, consent grants, or automatic retries."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid


def az(*args):
    process = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError("Azure operation failed; no automatic retry was attempted.")
    return json.loads(process.stdout) if process.stdout.strip() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    uuid.UUID(args.tenant)
    target = Path(".local/tenant-objects.json")
    if target.exists():
        raise RuntimeError("A local object manifest already exists; inspect it instead of recreating objects.")
    account = az("account", "show")
    if account["tenantId"] != args.tenant:
        raise RuntimeError("Active Azure tenant does not match the requested tenant.")
    plan = {
        "create": ["single-tenant confidential API app", "API service principal",
                   "single-tenant desktop public client", "public client service principal"],
        "automatic_consent": False,
        "credential_creation": False,
        "role_assignments": False,
    }
    print(json.dumps(plan, indent=2))
    if not args.apply:
        return
    if input("Type CREATE LAB APPLICATIONS to approve these four objects: ") != "CREATE LAB APPLICATIONS":
        raise RuntimeError("Approval not provided.")
    target.parent.mkdir(mode=0o700, exist_ok=True)
    os.chmod(target.parent, 0o700)
    manifest = {"tenant_id": args.tenant, "objects": [], "complete": False}

    def persist():
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(manifest, output, indent=2)

    # Save each successful write immediately so interrupted runs are inspectable.
    persist()
    scope_id = str(uuid.uuid4())
    api = az(
        "ad", "app", "create", "--display-name", "foundry-identity-lab-api",
        "--sign-in-audience", "AzureADMyOrg",
    )
    manifest["objects"].append({"kind": "api-app", "id": api["id"], "appId": api["appId"]})
    persist()
    patch = {
        "identifierUris": [f"api://{api['appId']}"],
        "api": {"requestedAccessTokenVersion": 2, "oauth2PermissionScopes": [{
            "id": scope_id, "value": "access_as_user", "type": "User", "isEnabled": True,
            "adminConsentDisplayName": "Access the identity lab",
            "adminConsentDescription": "Invoke identity lab experiments as the signed-in user.",
            "userConsentDisplayName": "Access the identity lab",
            "userConsentDescription": "Invoke identity lab experiments as you.",
        }]},
    }
    az("rest", "--method", "PATCH", "--url", f"https://graph.microsoft.com/v1.0/applications/{api['id']}",
       "--body", json.dumps(patch))
    sp = az("ad", "sp", "create", "--id", api["appId"])
    manifest["objects"].append({"kind": "api-sp", "id": sp["id"]})
    persist()
    public = az(
        "ad", "app", "create", "--display-name", "foundry-identity-lab-desktop",
        "--sign-in-audience", "AzureADMyOrg", "--public-client-redirect-uris", "http://localhost",
    )
    manifest["objects"].append({"kind": "public-app", "id": public["id"], "appId": public["appId"]})
    persist()
    sp = az("ad", "sp", "create", "--id", public["appId"])
    manifest["objects"].append({"kind": "public-sp", "id": sp["id"]})
    manifest["complete"] = True
    persist()
    print("Created four objects. Details are local only; configure permissions and consent explicitly.")


if __name__ == "__main__":
    main()
