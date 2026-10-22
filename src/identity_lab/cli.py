"""Interactive live runner; tokens stay in memory and raw identities stay local."""

import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path

from .catalog import PATTERNS
from .evidence import evaluate, extract_probe
from .transport import invoke, require_https, responses_url


def load_config(path: str) -> dict:
    file = Path(path).resolve()
    directory = Path.cwd().resolve() / ".local"
    if directory.is_symlink() or not file.is_relative_to(directory):
        raise ValueError("Tenant configuration must live under .local/.")
    config = json.loads(file.read_text())
    for key in ("project_endpoint", "api_endpoint"):
        require_https(config[key], local=key == "api_endpoint")
    return config


def sign_in(config: dict, alias: str, scopes: list[str]) -> str:
    import msal
    client = msal.PublicClientApplication(
        config["public_client_id"],
        authority=f"https://login.microsoftonline.com/{config['tenant_id']}",
    )
    print(f"Sign in as {alias}; credentials and tokens are not written to disk.")
    result = client.acquire_token_interactive(scopes=scopes, prompt="select_account")
    if "access_token" not in result:
        raise PermissionError("Interactive token acquisition failed.")
    return result["access_token"]


async def run(args) -> int:
    import httpx
    config = load_config(args.config)
    private = Path(".local/evidence")
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(private, 0o700)
    results = []
    observations = {}
    for alias in ("user-a", "user-b"):
        user_token = await asyncio.to_thread(
            sign_in, config, alias, ["https://ai.azure.com/.default"],
        )
        api_token = await asyncio.to_thread(
            sign_in, config, alias, [f"api://{config['api_client_id']}/access_as_user"],
        )
        # Both interactive grants must represent the same user. Compare locally
        # against Graph-independent oid/tid claims only after token acquisition.
        import jwt
        user_claims = jwt.decode(user_token, options={"verify_signature": False})
        api_claims = jwt.decode(api_token, options={"verify_signature": False})
        if any(user_claims.get(k) != api_claims.get(k) for k in ("oid", "tid")):
            raise PermissionError("Foundry and API sign-ins must use the same user.")
        if not user_claims.get("oid") or user_claims.get("tid") != config["tenant_id"]:
            raise PermissionError("The sign-in must use the configured tenant.")
        if alias == "user-b" and user_claims["oid"] == observations["user-a"]["oid"]:
            raise PermissionError("Use two distinct test users.")
        baseline_body = await invoke(
            responses_url(config["project_endpoint"], config["agent_b"]),
            user_token, {}, "Report the trusted request identity.",
        )
        baseline = extract_probe(baseline_body).get("user_id")
        if not baseline:
            raise RuntimeError("Direct B invocation returned no trusted user identity.")
        observations[alias] = {"baseline": baseline, "oid": user_claims["oid"], "cases": {}}
        for pattern, (_, mode, route) in PATTERNS.items():
            for configuration in ("user", "service", "drop-context"):
                case = f"{pattern}/{configuration}"
                if route == "probe" and configuration != "user":
                    continue
                if args.pattern and pattern != args.pattern:
                    continue
                try:
                    if mode == "direct":
                        body = await invoke(
                            responses_url(config["project_endpoint"], config["agent_a"]),
                            user_token,
                            {"x-client-route": route, "x-client-configuration": configuration},
                            "Report the trusted request identity.",
                        )
                    else:
                        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as client:
                            response = await client.post(
                                config["api_endpoint"] + "/invoke",
                                headers={"Authorization": f"Bearer {api_token}"},
                                json={"pattern": pattern, "configuration": configuration},
                            )
                            response.raise_for_status()
                            body = response.json()
                    probe = extract_probe(body)
                    observed = probe.get("user_id")
                    observations[alias]["cases"][case] = observed
                    result = evaluate(pattern, configuration, baseline, observed)
                except httpx.HTTPStatusError as error:
                    # A gateway 401/403 is not proof of target authorization.
                    # Keep negative failures blocked unless B's identity is observed.
                    result = replace(evaluate(pattern, configuration, baseline, None, blocked=True), reason="http-error")
                    observations[alias]["cases"][case] = {"http_status": error.response.status_code}
                except (ValueError, RuntimeError, httpx.RequestError):
                    result = replace(evaluate(pattern, configuration, baseline, None, blocked=True), reason="probe-unavailable")
                results.append({"alias": alias, **result.public()})
    if observations["user-a"]["baseline"] == observations["user-b"]["baseline"]:
        raise RuntimeError("Two distinct users produced the same trusted baseline.")
    for row in results:
        case = f"{row['pattern']}/{row['configuration']}"
        left = observations["user-a"]["cases"].get(case)
        right = observations["user-b"]["cases"].get(case)
        if row["configuration"] == "user" and isinstance(left, str) and left == right:
            row.update(status="FAIL", reason="cross-user-collision")
    raw = private / "latest.json"
    descriptor = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(observations, output, indent=2)
    # Candidate public evidence still requires review before committing.
    candidate = private / "public-candidate.json"
    descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump({"schema": 1, "results": results}, output, indent=2)
    print(json.dumps({"results": results}, indent=2))
    return 1 if any(row["status"] != "PASS" for row in results) else 0


def main():
    import httpx
    import jwt
    from azure.core.exceptions import AzureError
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=".local/config.json")
    parser.add_argument("--pattern", choices=PATTERNS)
    args = parser.parse_args()
    try:
        code = asyncio.run(run(args))
    except (OSError, ValueError, RuntimeError, KeyError, httpx.HTTPError, AzureError, jwt.PyJWTError) as error:
        # Only our fixed messages are public-safe; never print HTTP/token bodies.
        print(f"Lab stopped: {type(error).__name__}. Check local configuration and prerequisites.")
        code = 2
    raise SystemExit(code)


if __name__ == "__main__":
    main()
