"""Authenticated middleware API and custom MCP-to-Foundry wrapper."""

import asyncio
from contextlib import asynccontextmanager
import os
import re

from .auth import USER_CLAIMS, USER_TOKEN, obo, validate, workload_credential
from .catalog import PATTERNS
from .telemetry import Telemetry, TraceBoundary, annotate, operation
from .transport import FOUNDRY_SCOPE, invoke, responses_url


def create_app():
    import httpx
    import jwt
    from azure.core.exceptions import AzureError
    from fastapi import FastAPI, HTTPException
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings
    from pydantic import BaseModel
    from starlette.responses import JSONResponse

    required = ("LAB_TENANT_ID", "LAB_API_CLIENT_ID", "LAB_API_CLIENT_SECRET",
                "FOUNDRY_PROJECT_ENDPOINT", "LAB_AGENT_A_NAME", "LAB_AGENT_B_NAME")
    if any(not os.environ.get(key) for key in required):
        raise RuntimeError("Required API configuration is missing.")
    responses_url(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["LAB_AGENT_A_NAME"])
    responses_url(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["LAB_AGENT_B_NAME"])

    public_host = os.environ.get("LAB_PUBLIC_HOST", "")
    if public_host and not re.fullmatch(r"[A-Za-z0-9.-]+(?::[0-9]+)?", public_host):
        raise ValueError("LAB_PUBLIC_HOST must be one exact hostname with optional port.")
    allowed_hosts = ["localhost:*", "127.0.0.1:*"]
    allowed_origins = ["http://localhost:*", "http://127.0.0.1:*"]
    if public_host:
        allowed_hosts.append(public_host)
        allowed_origins.append(f"https://{public_host}")
    telemetry = Telemetry("identity-api")
    mcp = FastMCP(
        "identity-wrapper", stateless_http=True, json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts, allowed_origins=allowed_origins,
        ),
    )

    @mcp.tool()
    async def invoke_agent_b() -> dict:
        """Invoke Foundry B using an OBO token representing the authenticated user."""
        with operation("auth.obo"):
            token = await asyncio.to_thread(obo, USER_TOKEN.get())
        return await invoke(
            responses_url(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["LAB_AGENT_B_NAME"]),
            token, {}, "Report the trusted request identity.",
        )

    @asynccontextmanager
    async def lifespan(app):
        try:
            async with mcp.session_manager.run():
                yield
        finally:
            telemetry.close()

    app = FastAPI(lifespan=lifespan)

    @app.exception_handler(httpx.HTTPError)
    async def upstream_error(request, error):
        return JSONResponse({"error": "Upstream Foundry request failed."}, status_code=502)

    @app.exception_handler(AzureError)
    async def credential_error(request, error):
        return JSONResponse({"error": "Workload authentication failed."}, status_code=502)

    @app.exception_handler(RuntimeError)
    async def protocol_error(request, error):
        return JSONResponse({"error": "Upstream protocol operation failed."}, status_code=502)

    class Invocation(BaseModel):
        pattern: str
        configuration: str = "user"

    @app.get("/health")
    async def health():
        return {"status": "ready"}

    @app.post("/invoke")
    async def run(body: Invocation):
        if body.pattern not in PATTERNS or body.configuration not in ("user", "service", "drop-context"):
            raise HTTPException(400, "Unknown scenario.")
        _, mode, route = PATTERNS[body.pattern]
        if mode == "direct":
            raise HTTPException(400, "This pattern must bypass middleware.")
        annotate({"lab.pattern": body.pattern, "lab.configuration": body.configuration, "lab.route": route})
        headers = {"x-client-route": route, "x-client-configuration": body.configuration}
        if mode == "obo":
            try:
                with operation("auth.obo"):
                    token = await asyncio.to_thread(obo, USER_TOKEN.get())
            except PermissionError:
                raise HTTPException(403, "Delegated token acquisition failed.") from None
        else:
            with operation("auth.workload"):
                async with workload_credential() as credential:
                    token = (await credential.get_token(FOUNDRY_SCOPE)).token
            headers["x-ms-user-identity"] = USER_CLAIMS.get()["oid"]
        return await invoke(
            responses_url(os.environ["FOUNDRY_PROJECT_ENDPOINT"], os.environ["LAB_AGENT_A_NAME"]),
            token, headers, "Report the trusted request identity.",
        )

    app.mount("/tools", mcp.streamable_http_app())

    class AuthBoundary(TraceBoundary):
        async def dispatch(self, scope, receive, send):
            if scope["type"] != "http" or scope["path"] == "/health":
                await self.inner(scope, receive, send)
                return
            from starlette.datastructures import Headers
            authorization = Headers(scope=scope).get("authorization", "")
            if not authorization.startswith("Bearer "):
                await JSONResponse({"error": "Authentication required."}, status_code=401)(scope, receive, send)
                return
            token = authorization[7:]
            try:
                claims = await asyncio.to_thread(validate, token)
            except jwt.PyJWTError:
                await JSONResponse({"error": "Invalid delegated token."}, status_code=401)(scope, receive, send)
                return
            token_context = USER_TOKEN.set(token)
            claims_context = USER_CLAIMS.set(claims)
            try:
                await self.inner(scope, receive, send)
            finally:
                USER_CLAIMS.reset(claims_context)
                USER_TOKEN.reset(token_context)

    return AuthBoundary(app, telemetry, "api.request")
