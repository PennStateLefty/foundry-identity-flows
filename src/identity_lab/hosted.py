"""Deterministic hosted A/B agents; no model decides identity or destinations."""

import json
import os
from contextlib import asynccontextmanager

from .auth import workload_credential
from .telemetry import Telemetry, TraceBoundary, annotate, operation, trace_headers
from .transport import FOUNDRY_SCOPE, context_headers, invoke, require_https, responses_url


class HostedTraceBoundary(TraceBoundary):
    async def dispatch(self, scope, receive, send):
        # The SDK's response worker does not inherit the ASGI task's context.
        parent = trace_headers().get("x-client-traceparent")
        if scope["type"] == "http" and parent:
            headers = [(key, value) for key, value in scope["headers"]
                       if key.lower() != b"x-client-traceparent"]
            scope = {**scope, "headers": [*headers, (b"x-client-traceparent", parent.encode("ascii"))]}
        await super().dispatch(scope, receive, send)


async def call_toolbox(route: str, configuration: str, call_id: str | None) -> dict:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    suffix = "SERVICE" if configuration == "service" else "USER"
    endpoint = require_https(os.environ[f"TOOLBOX_{suffix}_ENDPOINT"])
    tool_name = os.environ[f"{route.upper()}_{suffix}_TOOL"]
    with operation("auth.workload"):
        async with workload_credential() as credential:
            token = (await credential.get_token(FOUNDRY_SCOPE)).token
    headers = {
        "Authorization": f"Bearer {token}",
        **context_headers(call_id, forward=configuration != "drop-context"),
    }
    with operation("foundry.toolbox"):
        async with httpx.AsyncClient(headers={**headers, **trace_headers()}, timeout=120, follow_redirects=False) as http:
            async with streamable_http_client(endpoint + "?api-version=v1", http_client=http) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    selected = next((tool for tool in tools.tools if tool.name == tool_name), None)
                    if selected is None:
                        raise ValueError("Configured toolbox tool was not discovered.")
                    args = json.loads(os.environ.get(f"{route.upper()}_ARGS_JSON", "{}"))
                    required = selected.inputSchema.get("required", [])
                    if any(key not in args for key in required):
                        raise ValueError("Configure tool arguments from its discovered input schema.")
                    result = await session.call_tool(tool_name, args)
                    if result.isError:
                        raise RuntimeError("Toolbox tool reported an error.")
                    return result.model_dump(mode="json")


def create_server():
    from azure.ai.agentserver.core import get_request_context
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse

    server = ResponsesAgentServerHost(configure_observability=None, access_log=None)
    telemetry = Telemetry(os.environ.get("LAB_TELEMETRY_ROLE", "identity-agent"))
    original_lifespan = server.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with original_lifespan(app) as state:
                yield state
        finally:
            telemetry.close()

    server.router.lifespan_context = lifespan
    server.add_middleware(HostedTraceBoundary, telemetry=telemetry, name="agent.request")

    @server.response_handler
    async def handle(request, context, cancellation_signal):
        with telemetry.span("agent.handler", parent=context.client_headers.get("x-client-traceparent")):
            current = get_request_context()
            route = context.client_headers.get("x-client-route", "probe")
            configuration = context.client_headers.get("x-client-configuration", "user")
            if configuration not in ("user", "service", "drop-context"):
                raise ValueError("Unknown identity configuration.")
            if route in ("probe", "chain", "a2a", "mcp"):
                annotate({"lab.route": route, "lab.configuration": configuration})
            if route == "probe":
                result = {
                    "kind": "identity-probe-v1",
                    "user_id": current.user_id,
                    "call_context_present": bool(current.call_id),
                }
            elif route == "chain":
                with operation("auth.workload"):
                    async with workload_credential() as credential:
                        token = (await credential.get_token(FOUNDRY_SCOPE)).token
                result = await invoke(
                    responses_url(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["LAB_AGENT_B_NAME"]),
                    token,
                    context_headers(current.call_id, forward=configuration == "user"),
                    "Report the trusted request identity.",
                )
            elif route in ("a2a", "mcp"):
                result = await call_toolbox(route, configuration, current.call_id)
            else:
                raise ValueError("Unknown route.")
            return TextResponse(context, request, text=json.dumps(result))

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":
    main()
