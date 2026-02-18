"""
OpenTelemetry bootstrap and structured-logging helpers for On-Call Copilot.

Provides:
  - configure_telemetry()  – call once at startup
  - get_tracer()           – returns the app-wide Tracer
  - new_correlation_id()   – UUID-based correlation ID generator
  - structured JSON logger via stdlib logging
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

_TRACER_NAME = "oncall-copilot"
_configured = False


def configure_telemetry(service_name: str = "oncall-copilot") -> None:
    """Initialise OTel tracer provider + structured JSON logging."""
    global _configured
    if _configured:
        return

    # --- OpenTelemetry tracing ---
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Console exporter for local dev; swap for OTLP exporter in production.
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
        except ImportError:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)

    # --- Structured logging ---
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    _configured = True


def get_tracer() -> trace.Tracer:
    return trace.get_tracer(_TRACER_NAME)


def new_correlation_id() -> str:
    return str(uuid.uuid4())
