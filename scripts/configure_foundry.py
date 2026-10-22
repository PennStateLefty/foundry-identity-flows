"""Enable B's A2A endpoint with an explicitly approved data-plane PATCH."""

import argparse
import asyncio
import json
import re


async def run(args):
    from azure.identity.aio import AzureCliCredential
    import httpx
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.agent):
        raise ValueError("Invalid agent name.")
    if not args.project.startswith("https://") or "?" in args.project:
        raise ValueError("An HTTPS project endpoint without a query is required.")
    payload = {
        "agent_card": {
            "description": "Deterministic identity propagation probe", "version": "1.0",
            "skills": [{"id": "probe", "name": "Identity probe", "description": "Return trusted runtime user context."}],
        },
        "agent_endpoint": {"protocol_configuration": {"responses": {}, "a2a": {}}},
    }
    print("Plan: enable Responses and A2A on the specified agent; no role grants.")
    if not args.apply:
        return
    if input("Type ENABLE A2A to approve the endpoint update: ") != "ENABLE A2A":
        raise RuntimeError("Approval not provided.")
    async with AzureCliCredential(tenant_id=args.tenant) as credential:
        token = (await credential.get_token("https://ai.azure.com/.default")).token
    async with httpx.AsyncClient(follow_redirects=False) as client:
        response = await client.patch(
            f"{args.project.rstrip('/')}/agents/{args.agent}?api-version=v1",
            headers={"Authorization": f"Bearer {token}"}, json=payload,
        )
    if not response.is_success:
        raise RuntimeError("Endpoint update failed. Do not publish the raw response.")
    print("Endpoint updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="identity-agent-b")
    parser.add_argument("--apply", action="store_true")
    asyncio.run(run(parser.parse_args()))
