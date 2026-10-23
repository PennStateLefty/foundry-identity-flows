import importlib.util
import json
import os
import unittest
from unittest.mock import patch

from identity_lab.telemetry import Telemetry, annotate, operation, record_status, trace_headers


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class TelemetryTests(unittest.TestCase):
    def setUp(self):
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        self.exporter = InMemorySpanExporter()
        self.environment = patch.dict(os.environ, {
            "LAB_TELEMETRY_ENABLED": "true",
            "LAB_APPLICATIONINSIGHTS_CONNECTION_STRING": "non-production-test-connection",
        })
        self.environment.start()
        self.export_patch = patch("azure.monitor.opentelemetry.exporter.AzureMonitorTraceExporter",
                                  return_value=self.exporter)
        self.export_factory = self.export_patch.start()
        self.credential_patch = patch("identity_lab.telemetry.workload_credential")
        self.credential_factory = self.credential_patch.start()
        self.telemetry = Telemetry("identity-api")
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.export_patch.stop)
        self.addCleanup(self.credential_patch.stop)
        self.addCleanup(self.telemetry.close)

    def spans(self):
        self.telemetry.provider.force_flush()
        return self.exporter.get_finished_spans()

    def test_explicit_entra_credential_and_no_offline_or_automatic_content_capture(self):
        self.credential_factory.assert_called_once_with(asynchronous=False)
        self.assertTrue(self.export_factory.call_args.kwargs["disable_offline_storage"])
        self.assertIs(self.export_factory.call_args.kwargs["tracer_provider"], self.telemetry.provider)
        self.assertEqual(os.environ["APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL"], "true")
        self.assertEqual(os.environ["APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED"], "true")

    def test_error_text_and_user_data_are_not_exported(self):
        with self.assertRaisesRegex(RuntimeError, "NEVER_EXPORT_ERROR"):
            with self.telemetry.span("api.request", attributes={"http.route": "/invoke"}):
                annotate({"lab.pattern": "P02", "lab.configuration": "user", "lab.route": "probe"})
                with operation("auth.obo"):
                    raise RuntimeError("NEVER_EXPORT_ERROR containing sensitive upstream details.")
        from opentelemetry.trace import StatusCode
        spans = self.spans()
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(s.status.status_code == StatusCode.ERROR for s in spans))
        text = " ".join(s.to_json() for s in spans)
        self.assertNotIn("NEVER_EXPORT_ERROR", text)
        self.assertTrue(all(not s.events for s in spans))
        self.assertEqual(trace_headers(), {})

    def test_arbitrary_identity_attributes_are_rejected(self):
        for values in ({"user.id": "NEVER_EXPORT_USER"}, {"lab.pattern": "NEVER_EXPORT_PATTERN"}):
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                with self.telemetry.span("api.request", attributes=values):
                    self.fail("Unexpected telemetry attribute was accepted.")
        self.assertFalse(self.spans())

    def test_operational_error_code_is_allowlisted_without_raw_error_text(self):
        with self.telemetry.span("agent.handler"):
            annotate({"lab.error.code": "toolbox-not-configured"})
            record_status(503)
        span = self.spans()[0]
        self.assertEqual(span.attributes["lab.error.code"], "toolbox-not-configured")
        self.assertEqual(span.attributes["http.response.status_code"], 503)
        with self.assertRaisesRegex(ValueError, "allowlisted"):
            annotate_values = {"lab.error.code": "private-arbitrary-exception"}
            with self.telemetry.span("agent.handler", attributes=annotate_values):
                pass

    def test_headers_preserve_only_w3c_trace_context(self):
        with self.telemetry.span("api.request"):
            with operation("foundry.responses"):
                headers = trace_headers()
                record_status(503)
        self.assertEqual(set(headers), {"traceparent", "x-client-traceparent"})
        self.assertEqual(headers["traceparent"], headers["x-client-traceparent"])
        root, dependency = sorted(self.spans(), key=lambda s: s.start_time)
        self.assertEqual(dependency.parent.span_id, root.context.span_id)
        self.assertEqual(dependency.context.trace_id, root.context.trace_id)
        self.assertEqual(dependency.attributes["http.response.status_code"], 503)

    def test_enabled_missing_connection_is_an_error(self):
        with patch.dict(os.environ, {"LAB_APPLICATIONINSIGHTS_CONNECTION_STRING": ""}):
            with self.assertRaisesRegex(ValueError, "requires its explicit"):
                Telemetry("identity-api")

    def test_azure_envelopes_preserve_http_result_codes_without_content(self):
        from azure.monitor.opentelemetry.exporter.export.trace._exporter import _convert_span_to_envelope
        with self.telemetry.span("api.request", attributes={
            "http.route": "/invoke", "http.request.method": "POST",
        }):
            with operation("foundry.responses", attributes={"http.request.method": "POST"}):
                record_status(503)
            record_status(401)
        envelopes = [_convert_span_to_envelope(span) for span in self.spans()]
        request = next(e.data.base_data for e in envelopes if e.data.base_type == "RequestData")
        dependency = next(e.data.base_data for e in envelopes if e.data.base_type == "RemoteDependencyData")
        self.assertEqual(request["responseCode"], "401")
        self.assertEqual(dependency["resultCode"], "503")
        self.assertFalse(request["success"])
        self.assertFalse(dependency["success"])
        self.assertEqual(dependency["type"], "HTTP")
        serialized = json.dumps([e.as_dict() for e in envelopes])
        self.assertNotIn("non-production-test-connection", serialized)
        self.assertNotIn("NEVER_EXPORT", serialized)
        self.assertFalse(request.get("url"))
        self.assertFalse(dependency.get("data"))

    def test_sync_workload_credentials_have_no_developer_fallback(self):
        from identity_lab.auth import workload_credential
        with patch.dict(os.environ, {
            "LAB_WORKLOAD_AUTH": "platform", "AZURE_FEDERATED_TOKEN_FILE": "",
            "AZURE_CLIENT_ID": "test-workload", "LAB_TENANT_ID": "test-tenant",
        }), patch("azure.identity.ManagedIdentityCredential") as managed, \
             patch("azure.identity.WorkloadIdentityCredential") as federated, \
             patch("azure.identity.AzureCliCredential") as cli:
            self.assertIs(workload_credential(asynchronous=False), managed.return_value)
            managed.assert_called_once_with(client_id="test-workload")
            cli.assert_not_called()
            with patch.dict(os.environ, {"AZURE_FEDERATED_TOKEN_FILE": "/synthetic-token"}):
                self.assertIs(workload_credential(asynchronous=False), federated.return_value)
                federated.assert_called_once_with()
            with patch.dict(os.environ, {"LAB_WORKLOAD_AUTH": "azure-cli"}):
                self.assertIs(workload_credential(asynchronous=False), cli.return_value)
                cli.assert_called_once_with(tenant_id="test-tenant")

    def test_disabled_telemetry_does_not_create_an_exporter(self):
        self.export_factory.reset_mock()
        with patch.dict(os.environ, {"LAB_TELEMETRY_ENABLED": "false"}):
            telemetry = Telemetry("identity-api")
            with telemetry.span("api.request"):
                self.assertEqual(trace_headers(), {})
            telemetry.close()
        self.export_factory.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("fastapi"), "Runtime dependencies are not installed.")
class TelemetryRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
        self.exporter = InMemorySpanExporter()
        for context in (
            patch.dict(os.environ, {
                "LAB_TELEMETRY_ENABLED": "true",
                "LAB_APPLICATIONINSIGHTS_CONNECTION_STRING": "non-production-test-connection",
                "LAB_TENANT_ID": "test-tenant", "LAB_API_CLIENT_ID": "test-application",
                "LAB_API_CLIENT_SECRET": "NEVER_EXPORT_SECRET",
                "FOUNDRY_PROJECT_ENDPOINT": "https://example.com/api/projects/test",
                "LAB_AGENT_A_NAME": "agent-a", "LAB_AGENT_B_NAME": "agent-b",
            }),
            patch("azure.monitor.opentelemetry.exporter.AzureMonitorTraceExporter", return_value=self.exporter),
            patch("identity_lab.telemetry.workload_credential"),
        ):
            context.start()
            self.addCleanup(context.stop)

    async def test_authentication_denials_are_traced_without_headers_or_query_strings(self):
        import httpx
        from identity_lab.api import create_app
        app = create_app()
        async with app.inner.router.lifespan_context(app.inner):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/invoke?secret=NEVER_EXPORT_QUERY")
                self.assertEqual(response.status_code, 401)
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].attributes["http.response.status_code"], 401)
        self.assertNotIn("NEVER_EXPORT", spans[0].to_json())

    async def test_response_status_survives_an_isolated_sdk_sender_context(self):
        import asyncio
        from contextvars import Context
        import httpx
        from azure.monitor.opentelemetry.exporter.export.trace._exporter import _convert_span_to_envelope
        from identity_lab.telemetry import TraceBoundary

        async def endpoint(scope, receive, send):
            async def respond():
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b""})
            await Context().run(asyncio.create_task, respond())

        telemetry = Telemetry("identity-agent-b")
        try:
            app = TraceBoundary(endpoint, telemetry, "agent.request")
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post("/responses")
            self.assertEqual(response.status_code, 401)
        finally:
            telemetry.close()
        span, = self.exporter.get_finished_spans()
        self.assertEqual(span.attributes["http.response.status_code"], 401)
        envelope = _convert_span_to_envelope(span)
        self.assertEqual(envelope.data.base_data["responseCode"], "401")
        self.assertFalse(envelope.data.base_data["success"])

    async def test_real_outbound_responses_dependency_has_safe_correlated_trace_headers(self):
        import httpx
        from identity_lab.api import create_app
        app = create_app()
        outbound = []
        real_client = httpx.AsyncClient

        def respond(request):
            outbound.append(request)
            return httpx.Response(200, json={"status": "completed", "output": "NEVER_EXPORT_RESPONSE"})

        def outbound_client(*args, **kwargs):
            return real_client(*args, **kwargs, transport=httpx.MockTransport(respond))

        async with app.inner.router.lifespan_context(app.inner):
            async with real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                with patch("identity_lab.api.validate", return_value={"oid": "NEVER_EXPORT_USER"}), \
                     patch("identity_lab.api.obo", return_value="NEVER_EXPORT_TOKEN"), \
                     patch("httpx.AsyncClient", side_effect=outbound_client):
                    response = await client.post(
                        "/invoke", headers={"Authorization": "Bearer non-production-test-token"},
                        json={"pattern": "P02"},
                    )
                    self.assertEqual(response.status_code, 200)
        spans = self.exporter.get_finished_spans()
        self.assertEqual({s.name for s in spans}, {"api.request", "auth.obo", "foundry.responses"})
        self.assertEqual(len({s.context.trace_id for s in spans}), 1)
        self.assertEqual(outbound[0].headers["traceparent"], outbound[0].headers["x-client-traceparent"])
        self.assertEqual(outbound[0].headers["authorization"], "Bearer NEVER_EXPORT_TOKEN")
        self.assertNotIn("NEVER_EXPORT", " ".join(s.to_json() for s in spans))

    async def test_hosted_probe_is_returned_but_not_recorded_as_telemetry(self):
        import httpx
        from identity_lab.evidence import extract_probe
        from identity_lab.hosted import create_server
        try:
            app = create_server()
        except ModuleNotFoundError:
            self.skipTest("Hosted dependency is not installed.")
        parent = "00-" + "1" * 32 + "-" + "2" * 16 + "-01"
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/responses",
                    headers={"x-agent-user-id": "NEVER_EXPORT_USER", "x-agent-foundry-call-id": "NEVER_EXPORT_CALL",
                             "x-client-traceparent": parent},
                    json={"input": "NEVER_EXPORT_INPUT", "stream": False, "store": False},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(extract_probe(response.json())["user_id"], "NEVER_EXPORT_USER")
        spans = self.exporter.get_finished_spans()
        self.assertEqual(len(spans), 2)
        request = next(s for s in spans if s.name == "agent.request")
        handler = next(s for s in spans if s.name == "agent.handler")
        self.assertEqual(request.context.trace_id, int("1" * 32, 16))
        self.assertEqual(request.parent.span_id, int("2" * 16, 16))
        self.assertEqual(handler.context.trace_id, request.context.trace_id)
        self.assertEqual(handler.parent.span_id, request.context.span_id)
        self.assertEqual(handler.attributes["lab.route"], "probe")
        self.assertEqual(handler.attributes["lab.configuration"], "user")
        self.assertNotIn("NEVER_EXPORT", " ".join(s.to_json() for s in spans))


if __name__ == "__main__":
    unittest.main()
