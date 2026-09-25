"""AEGIS-1303: OpenTelemetry Tracing.

Configures tracing for Guard.check() with child spans for each evaluation phase.
Exports to OTLP collector if AEGIS_TRACING_ENDPOINT is set.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Lazy-loaded tracer
_tracer: Any = None
_noop = True


def configure_tracing(service_name: str = "aegis-guard") -> None:
    """Configure OpenTelemetry tracing if endpoint is set."""
    global _tracer, _noop

    endpoint = os.getenv("AEGIS_TRACING_ENDPOINT", "")
    if not endpoint:
        logger.info("AEGIS_TRACING_ENDPOINT not set, tracing disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("aegis")
        _noop = False
        logger.info("Tracing configured, exporting to %s", endpoint)

    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed, tracing disabled. "
            "Install with: pip install aegis[ops]"
        )


@contextmanager
def trace_span(
    name: str,
    attributes: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Create a traced span. No-op if tracing is not configured."""
    if _noop or _tracer is None:
        yield None
        return

    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
        yield span
