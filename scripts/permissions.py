"""Declare only the delegated scopes needed by the two recorded lab apps."""

import argparse
import json
from pathlib import Path

from credential import az, save


def normalize_permissions(entries):
    return sorted(
        (entry["resourceAppId"], tuple(sorted((item["id"], item["type"])
                                            for item in entry["resourceAccess"])))
        for entry in entries or []
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    directory = Path(".local")
    if directory.is_symlink():
        raise ValueError("Local state must not be a symbolic link.")
    manifest = json.loads((directory / "tenant-objects.json").read_text())
    if not manifest["complete"] or manifest["tenant_id"] != args.tenant:
        raise ValueError("A completed bootstrap manifest for the approved tenant is required.")
    if az("account", "show")["tenantId"] != args.tenant:
        raise ValueError("Active tenant does not match the approved tenant.")
    apps = {}
    for kind in ("api-app", "public-app"):
        matches = [item for item in manifest["objects"] if item["kind"] == kind]
        if len(matches) != 1:
            raise ValueError("Exactly one registration of each lab app type is required.")
        apps[kind] = az("ad", "app", "show", "--id", matches[0]["id"])
    foundry = az("ad", "sp", "list", "--filter", "servicePrincipalNames/any(s:s eq 'https://ai.azure.com')")
    if len(foundry) != 1:
        raise ValueError("Exactly one existing Foundry resource service principal is required.")
    foundry_scopes = [s for s in foundry[0]["oauth2PermissionScopes"]
                      if s["value"] == "user_impersonation" and s["isEnabled"]]
    api_scopes = [s for s in apps["api-app"]["api"]["oauth2PermissionScopes"]
                  if s["value"] == "access_as_user" and s["isEnabled"]]
    if len(foundry_scopes) != 1 or len(api_scopes) != 1:
        raise ValueError("Required delegated permission definitions are absent or ambiguous.")
    foundry_permission = {
        "resourceAppId": foundry[0]["appId"],
        "resourceAccess": [{"id": foundry_scopes[0]["id"], "type": "Scope"}],
    }
    desired = {
        "api-app": [foundry_permission],
        "public-app": [
            foundry_permission,
            {"resourceAppId": apps["api-app"]["appId"],
             "resourceAccess": [{"id": api_scopes[0]["id"], "type": "Scope"}]},
        ],
    }
    for kind, app in apps.items():
        existing = normalize_permissions(app.get("requiredResourceAccess"))
        if existing and existing != normalize_permissions(desired[kind]):
            raise ValueError("Unexpected permission declarations exist; no fields will be overwritten.")
    print("Plan: API requests Foundry user_impersonation; desktop requests that scope and API access_as_user.")
    print("No consent grant, Graph permission, application permission, or Azure role will be created.")
    if not args.apply:
        return
    state = directory / "permission-declarations.json"
    if state.exists():
        raise RuntimeError("Declaration state exists; inspect it instead of automatically repeating writes.")
    if input("Type DECLARE DELEGATED SCOPES to approve these declarations: ") != "DECLARE DELEGATED SCOPES":
        raise RuntimeError("Approval not provided.")
    progress = {
        "tenant_id": args.tenant, "completed": [], "status": "pending",
        "applications": {kind: {"id": app["id"], "requiredResourceAccess": desired[kind]}
                         for kind, app in apps.items()},
    }
    save(state, progress, exclusive=True)
    for kind, app in apps.items():
        progress["current"] = kind
        save(state, progress)
        current = az("ad", "app", "show", "--id", app["id"])
        if normalize_permissions(current.get("requiredResourceAccess")) != normalize_permissions(
            app.get("requiredResourceAccess")
        ):
            raise RuntimeError("Permission declarations changed during approval; inspect state before proceeding.")
        if normalize_permissions(current.get("requiredResourceAccess")) != normalize_permissions(desired[kind]):
            az("rest", "--method", "PATCH",
               "--url", f"https://graph.microsoft.com/v1.0/applications/{app['id']}",
               "--body", json.dumps({"requiredResourceAccess": desired[kind]}))
        actual = az("ad", "app", "show", "--id", app["id"])
        if normalize_permissions(actual.get("requiredResourceAccess")) != normalize_permissions(desired[kind]):
            raise RuntimeError("Permission declarations could not be verified; do not repeat the write automatically.")
        progress["completed"].append(kind)
        save(state, progress)
    progress.pop("current")
    save(state, {**progress, "status": "complete"})
    print("Delegated permission declarations configured. Consent remains a separate operator decision.")


if __name__ == "__main__":
    main()
