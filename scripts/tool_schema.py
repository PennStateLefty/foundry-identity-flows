"""Keep discovered toolbox names and schemas local for explicit configuration."""

import argparse
import asyncio
import json
import os
from pathlib import Path


async def run(args):
    from azure.identity.aio import AzureCliCredential
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from identity_lab.transport import require_https
    endpoint = require_https(args.endpoint)
    async with AzureCliCredential(tenant_id=args.tenant) as credential:
        token = (await credential.get_token("https://ai.azure.com/.default")).token
    async with httpx.AsyncClient(headers={"Authorization": f"Bearer {token}"}, follow_redirects=False) as http:
        async with streamable_http_client(endpoint + "?api-version=v1", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
    directory = Path(".local")
    directory.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(directory / "tool-schemas.json", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(tools.model_dump(mode="json"), output, indent=2)
    print("Wrote local tool schemas. Do not publish discovered server metadata.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--endpoint", required=True)
    asyncio.run(run(parser.parse_args()))
