from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


_LOCK = threading.RLock()
_CONFIGURED = False
_STATUS: dict[str, object] = {
    "otel_enabled": False,
    "cloud_trace_enabled": False,
    "configured": False,
    "exporter": "none",
}


def configure_observability(settings) -> dict[str, object]:
    """Configure OpenTelemetry once without ever making app startup depend on tracing."""
    global _CONFIGURED, _STATUS
    with _LOCK:
        if _CONFIGURED:
            return dict(_STATUS)
        _CONFIGURED = True
        enabled = bool(getattr(settings, "otel_enabled", False))
        cloud_trace = bool(getattr(settings, "cloud_trace_enabled", False))
        _STATUS = {
            "otel_enabled": enabled,
            "cloud_trace_enabled": cloud_trace,
            "configured": False,
            "exporter": "none",
        }
        if not enabled:
            return dict(_STATUS)
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider(
                resource=Resource.create(
                    {
                        "service.name": str(getattr(settings, "otel_service_name", "healthia-one")),
                        "service.version": str(getattr(settings, "release_sha", "local"))[:40],
                    }
                )
            )
            if cloud_trace:
                from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

                provider.add_span_processor(BatchSpanProcessor(CloudTraceSpanExporter()))
                _STATUS["exporter"] = "google_cloud_trace"
            trace.set_tracer_provider(provider)
            _STATUS["configured"] = True
        except Exception as exc:
            _STATUS["error"] = type(exc).__name__
        return dict(_STATUS)


def observability_status() -> dict[str, object]:
    return dict(_STATUS)


@contextmanager
def span(name: str, **attributes: object) -> Iterator[object | None]:
    """Create a sanitized span. Callers must never pass raw PHI or prompt text."""
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("healthia-one")
        with tracer.start_as_current_span(name) as current:
            for key, value in attributes.items():
                if value is not None and isinstance(value, (str, bool, int, float)):
                    current.set_attribute(f"healthia.{key}", value)
            yield current
    except Exception:
        yield None
