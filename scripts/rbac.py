"""Apply one operator-reviewed RBAC grant using an explicit tenant and scope."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def command(*args):
    result = subprocess.run(["az", *args, "-o", "json"], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("RBAC operation failed; inspect locally without publishing output.")
    return json.loads(result.stdout) if result.stdout.strip() else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--principal", required=True)
    parser.add_argument("--principal-type", choices=("User", "Group", "ServicePrincipal"), required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--role", choices=("Foundry Agent Consumer", "Foundry User", "AcrPull", "AcrPush", "impersonation"), required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if command("account", "show")["tenantId"] != args.tenant:
        raise RuntimeError("Tenant mismatch.")
    provider = "Microsoft.ContainerRegistry/registries/" if args.role in ("AcrPull", "AcrPush") else "Microsoft.CognitiveServices/accounts/"
    if f"/providers/{provider}".lower() not in args.scope.lower():
        raise ValueError("The resource scope does not match the requested role.")
    print(f"Plan: grant {args.role} to the specified principal at the specified Foundry scope.")
    if not args.apply:
        return
    if input("Type GRANT to approve this specific role assignment: ") != "GRANT":
        raise RuntimeError("Approval not provided.")
    role = args.role
    if role == "impersonation":
        if args.principal_type != "ServicePrincipal":
            raise ValueError("Impersonation grants are restricted to backend workloads.")
        role = "Foundry Identity Lab User Impersonation"
        existing = command("role", "definition", "list", "--name", role, "--scope", args.scope)
        if not existing:
            definition = {
                "Name": role, "IsCustom": True,
                "Description": "Explicit represented-user delegation for the identity lab.",
                "Actions": [], "NotActions": [],
                "DataActions": ["Microsoft.CognitiveServices/accounts/AIServices/agents/endpoints/UserIdentityImpersonation/action"],
                "NotDataActions": [], "AssignableScopes": [args.scope],
            }
            command("role", "definition", "create", "--role-definition", json.dumps(definition))
    assignments = command("role", "assignment", "list", "--assignee-object-id", args.principal, "--scope", args.scope)
    if any(item["roleDefinitionName"] == role and item["scope"].lower() == args.scope.lower() for item in assignments):
        print("The exact role assignment already exists.")
        return
    created = command(
        "role", "assignment", "create", "--assignee-object-id", args.principal,
        "--assignee-principal-type", args.principal_type, "--role", role, "--scope", args.scope,
    )
    directory = Path(".local/role-grants")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / f"grant-{len(list(directory.iterdir())) + 1}.json",
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(created, output, indent=2)
    print("Granted. Assignment details remain local.")


if __name__ == "__main__":
    main()
