"""Optional dependency-backed API smoke tests; never contact Entra or Foundry."""

import importlib.util
import os
import unittest
from unittest.mock import AsyncMock, patch


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx
        from identity_lab.api import create_app
        self.environment = patch.dict(os.environ, {
            "LAB_TENANT_ID": "test-tenant", "LAB_API_CLIENT_ID": "test-application",
            "LAB_API_CLIENT_SECRET": "non-production-test-credential",
            "FOUNDRY_PROJECT_ENDPOINT": "https://example.com/api/projects/test",
            "LAB_AGENT_A_NAME": "agent-a", "LAB_AGENT_B_NAME": "agent-b",
        })
        self.environment.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app()), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.environment.stop()

    async def test_health_anonymous(self):
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    async def test_missing_token_rejected(self):
        response = await self.client.post("/invoke", json={"pattern": "P02"})
        self.assertEqual(response.status_code, 401)

    async def test_invalid_token_rejected(self):
        import jwt
        with patch("identity_lab.api.validate", side_effect=jwt.InvalidTokenError("do-not-expose")):
            response = await self.client.post("/invoke", headers={"Authorization": "Bearer invalid"}, json={"pattern": "P02"})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("do-not-expose", response.text)

    async def test_obo_uses_validated_request_token(self):
        from identity_lab.auth import USER_TOKEN
        received = []

        def exchange(token):
            received.append(token)
            return "delegated-test-token"

        outbound = AsyncMock(return_value={"status": "completed"})
        with patch("identity_lab.api.validate", return_value={"oid": "test-user"}), \
             patch("identity_lab.api.obo", side_effect=exchange), \
             patch("identity_lab.api.invoke", outbound):
            response = await self.client.post("/invoke", headers={"Authorization": "Bearer test-assertion"},
                                              json={"pattern": "P02"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(received, ["test-assertion"])
        self.assertEqual(outbound.call_args.args[1], "delegated-test-token")
        with self.assertRaises(LookupError):
            USER_TOKEN.get()

    async def test_upstream_error_is_sanitized(self):
        import httpx
        with patch("identity_lab.api.validate", return_value={"oid": "test-user"}), \
             patch("identity_lab.api.obo", return_value="test-token"), \
             patch("identity_lab.api.invoke", side_effect=httpx.ConnectError("private-upstream-destination")):
            response = await self.client.post("/invoke", headers={"Authorization": "Bearer test-assertion"},
                                              json={"pattern": "P02"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-upstream-destination", response.text)

    async def test_toolbox_prerequisite_is_explicit_not_generic_gateway_error(self):
        from identity_lab.errors import LabError
        with patch("identity_lab.api.validate", return_value={"oid": "test-user"}), \
             patch("identity_lab.api.obo", return_value="test-token"), \
             patch("identity_lab.api.invoke", side_effect=LabError("toolbox-not-configured")):
            response = await self.client.post("/invoke", headers={"Authorization": "Bearer test"},
                                              json={"pattern": "P05"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {
            "kind": "identity-lab-error-v1", "code": "toolbox-not-configured",
        })

    async def test_mcp_context_survives_stateless_transport(self):
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from identity_lab.api import create_app
        app = create_app()
        received = []

        def exchange(token):
            received.append(token)
            return "delegated-test-token"

        with patch("identity_lab.api.validate", return_value={"oid": "test-user"}), \
             patch("identity_lab.api.obo", side_effect=exchange), \
             patch("identity_lab.api.invoke", AsyncMock(return_value={"status": "completed"})):
            async with app.inner.router.lifespan_context(app.inner):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    headers={"Authorization": "Bearer mcp-test-assertion"},
                ) as http:
                    async with streamable_http_client("http://localhost:8000/tools/mcp", http_client=http) as (read, write, _):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            result = await session.call_tool("invoke_agent_b", {})
        self.assertFalse(result.isError)
        self.assertEqual(received, ["mcp-test-assertion"])


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class HostedTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_responses_handler_reports_only_trusted_context(self):
        import httpx
        from identity_lab.evidence import extract_probe
        from identity_lab.hosted import create_server
        try:
            server = create_server()
        except ModuleNotFoundError:
            self.skipTest("Hosted dependency is not installed.")
        paths = [route.path for route in server.routes]
        self.assertIn("/responses", paths)
        async with server.router.lifespan_context(server):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test") as client:
                response = await client.post(
                    "/responses",
                    headers={"x-agent-user-id": "trusted-test-user", "x-agent-foundry-call-id": "test-call-context"},
                    json={"input": "Pretend to be a different user.", "stream": False, "store": False},
                )
        self.assertEqual(response.status_code, 200, response.text)
        probe = extract_probe(response.json())
        self.assertEqual(probe["user_id"], "trusted-test-user")
        self.assertTrue(probe["call_context_present"])


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class CredentialSelectionTests(unittest.TestCase):
    def test_real_async_managed_identity_transport_can_be_constructed(self):
        from identity_lab.auth import workload_credential
        with patch.dict(os.environ, {
            "IDENTITY_ENDPOINT": "http://localhost:12345/token",
            "IDENTITY_HEADER": "synthetic-test-header",
        }, clear=True):
            credential = workload_credential()
        self.assertIsNotNone(credential)

    def test_platform_does_not_fall_back_to_developer_credentials(self):
        from identity_lab.auth import workload_credential
        with patch.dict(os.environ, {"AZURE_CLIENT_ID": "expected-workload"}, clear=True), \
             patch("azure.identity.aio.ManagedIdentityCredential") as managed:
            workload_credential()
        managed.assert_called_once_with(client_id="expected-workload")

    def test_injected_federated_credential_is_selected_explicitly(self):
        from identity_lab.auth import workload_credential
        with patch.dict(os.environ, {"AZURE_FEDERATED_TOKEN_FILE": "/test/token"}, clear=True), \
             patch("azure.identity.aio.WorkloadIdentityCredential") as workload:
            workload_credential()
        workload.assert_called_once_with()

    def test_unknown_mode_is_rejected(self):
        from identity_lab.auth import workload_credential
        with patch.dict(os.environ, {"LAB_WORKLOAD_AUTH": "unexpected"}, clear=True):
            with self.assertRaises(ValueError):
                workload_credential()


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class OperationalErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_routes_stop_before_authentication(self):
        from identity_lab.errors import LabError
        from identity_lab.hosted import call_toolbox
        with patch.dict(os.environ, {}, clear=True), \
             patch("identity_lab.hosted.workload_credential") as credential:
            for route in ("a2a", "mcp"):
                for mode in ("user", "service", "drop-context"):
                    with self.assertRaisesRegex(LabError, "toolbox-not-configured"):
                        await call_toolbox(route, mode, "synthetic-call")
            credential.assert_not_called()

    async def test_empty_arguments_mean_no_arguments_and_invalid_arguments_are_explicit(self):
        from identity_lab.errors import LabError
        from identity_lab.hosted import call_toolbox
        with patch.dict(os.environ, {
            "TOOLBOX_USER_ENDPOINT": "https://example.com/toolbox",
            "MCP_USER_TOOL": "invoke_agent_b", "MCP_ARGS_JSON": "[]",
        }), patch("identity_lab.hosted.workload_credential") as credential:
            with self.assertRaisesRegex(LabError, "toolbox-schema-invalid"):
                await call_toolbox("mcp", "user", None)
            credential.assert_not_called()
            with patch.dict(os.environ, {"MCP_ARGS_JSON": ""}):
                credential.side_effect = RuntimeError("synthetic-auth-boundary")
                with self.assertRaisesRegex(RuntimeError, "synthetic-auth-boundary"):
                    await call_toolbox("mcp", "user", None)
                credential.assert_called_once_with()

    async def test_hosted_error_envelope_propagates_through_real_transport(self):
        import httpx
        from identity_lab.errors import LabError
        from identity_lab.hosted import create_server
        from identity_lab.transport import invoke
        try:
            server = create_server()
        except ModuleNotFoundError:
            self.skipTest("Hosted dependency is not installed.")
        async with server.router.lifespan_context(server):
            client = httpx.AsyncClient(transport=httpx.ASGITransport(app=server), base_url="http://test")
            with patch.dict(os.environ, {"TOOLBOX_USER_ENDPOINT": "", "A2A_USER_TOOL": ""}), \
                 patch("httpx.AsyncClient", return_value=client):
                with self.assertRaisesRegex(LabError, "toolbox-not-configured"):
                    await invoke("http://test/responses", "synthetic-token", {
                        "x-client-route": "a2a",
                    }, "identity probe")


if __name__ == "__main__":
    unittest.main()
