"""Explicit, content-free operational tracing for the private lab workspace."""

from contextlib import contextmanager
from contextvars import ContextVar
import os
import re

from .auth import workload_credential
from .catalog import PATTERNS
from .errors import ERROR_STATUS

_ACTIVE: ContextVar = ContextVar("lab_telemetry", default=None)
_OPERATIONS = {
    "api.request", "agent.request", "agent.handler", "foundry.responses", "foundry.toolbox",
    "auth.obo", "auth.workload",
}
_VALUES = {
    "http.route": {"/health", "/invoke", "/tools/mcp", "/responses", "other"},
    "http.request.method": {"GET", "POST", "_OTHER"},
    "lab.pattern": set(PATTERNS),
    "lab.configuration": {"user", "service", "drop-context"},
    "lab.route": {"probe", "chain", "a2a", "mcp"},
    "lab.error.code": set(ERROR_STATUS),
}


def _attributes(values):
    result = {}
    for key, value in (values or {}).items():
        if key == "http.response.status_code" and type(value) is int and 100 <= value <= 599:
            result[key] = value
        elif key in _VALUES and value in _VALUES[key]:
            result[key] = value
        else:
            raise ValueError("Telemetry accepts only fixed, allowlisted operational attributes.")
    return result


class Telemetry:
    def __init__(self, role: str):
        if role not in {"identity-api", "identity-agent", "identity-agent-a", "identity-agent-b"}:
            raise ValueError("Unknown telemetry service role.")
        mode = os.environ.get("LAB_TELEMETRY_ENABLED", "false")
        if mode not in {"true", "false"}:
            raise ValueError("LAB_TELEMETRY_ENABLED must be true or false.")
        self.provider = None
        self.credential = None
        if mode == "false":
            return
        connection = os.environ.get("LAB_APPLICATIONINSIGHTS_CONNECTION_STRING")
        if not connection:
            raise ValueError("Enabled lab telemetry requires its explicit Application Insights connection string.")
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON

        os.environ["APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL"] = "true"
        os.environ["APPLICATIONINSIGHTS_CONTROLPLANE_DISABLED"] = "true"
        self.credential = workload_credential(asynchronous=False)
        provider = TracerProvider(resource=Resource({"service.name": role}), sampler=ALWAYS_ON)
        initialized = False
        try:
            exporter = AzureMonitorTraceExporter(
                connection_string=connection, credential=self.credential,
                tracer_provider=provider,
                disable_offline_storage=True, timeout=5,
            )
            initialized = True
        finally:
            if not initialized:
                try:
                    provider.shutdown()
                finally:
                    self.credential.close()
        self.provider = provider
        self.provider.add_span_processor(BatchSpanProcessor(exporter))
        self.tracer = self.provider.get_tracer("identity-lab")

    @contextmanager
    def span(self, name: str, *, attributes=None, parent=None):
        if name not in _OPERATIONS:
            raise ValueError("Unknown operational span.")
        attributes = _attributes(attributes)
        active = _ACTIVE.set(self if self.provider else None)
        try:
            if self.provider is None:
                yield
                return
            from opentelemetry.trace import SpanKind, Status, StatusCode
            from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

            valid_parent = isinstance(parent, str) and re.fullmatch(
                r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", parent
            )
            context = TraceContextTextMapPropagator().extract({"traceparent": parent}) if valid_parent else None
            kind = (SpanKind.SERVER if name.endswith(".request") else
                    SpanKind.CLIENT if name.startswith("foundry.") else SpanKind.INTERNAL)
            with self.tracer.start_as_current_span(
                name, context=context, kind=kind, attributes=attributes,
                record_exception=False, set_status_on_exception=False,
            ) as span:
                completed = False
                try:
                    yield span
                    completed = True
                finally:
                    if not completed:
                        span.set_status(Status(StatusCode.ERROR))
        finally:
            _ACTIVE.reset(active)

    def close(self):
        if self.provider is not None:
            try:
                self.provider.shutdown()
            finally:
                self.credential.close()


@contextmanager
def operation(name, *, attributes=None):
    telemetry = _ACTIVE.get()
    if telemetry is None:
        yield
    else:
        with telemetry.span(name, attributes=attributes):
            yield


def annotate(values):
    if _ACTIVE.get() is not None:
        from opentelemetry.trace import get_current_span
        get_current_span().set_attributes(_attributes(values))


def record_status(code, *, span=None):
    if span is not None or _ACTIVE.get() is not None:
        from opentelemetry.trace import Status, StatusCode, get_current_span
        if span is None:
            span = get_current_span()
        span.set_attributes(_attributes({"http.response.status_code": code}))
        if code >= 400:
            span.set_status(Status(StatusCode.ERROR))


def trace_headers():
    if _ACTIVE.get() is None:
        return {}
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    carrier = {}
    TraceContextTextMapPropagator().inject(carrier)
    parent = carrier.get("traceparent")
    return {"traceparent": parent, "x-client-traceparent": parent} if parent else {}


class TraceBoundary:
    def __init__(self, app, telemetry, name):
        self.inner, self.telemetry, self.name = app, telemetry, name

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.dispatch(scope, receive, send)
            return
        from starlette.datastructures import Headers
        headers = Headers(scope=scope)
        path = scope["path"]
        route = path if path in _VALUES["http.route"] else "other"
        parent = headers.get("x-client-traceparent") or headers.get("traceparent")
        method = scope["method"] if scope["method"] in {"GET", "POST"} else "_OTHER"
        with self.telemetry.span(
            self.name, attributes={"http.route": route, "http.request.method": method}, parent=parent,
        ) as span:
            started = False

            async def traced_send(message):
                nonlocal started
                if message["type"] == "http.response.start":
                    started = True
                    record_status(message["status"], span=span)
                await send(message)

            try:
                await self.dispatch(scope, receive, traced_send)
            finally:
                if not started:
                    record_status(500, span=span)

    async def dispatch(self, scope, receive, send):
        await self.inner(scope, receive, send)
