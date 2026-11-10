"""Optional OTLP export; disabled unless IRONCLAD_OTLP_ENDPOINT is configured."""

import os
import time

from .schema import Message

_initialized = False


def record(event: Message) -> None:
    global _initialized
    endpoint = os.environ.get("IRONCLAD_OTLP_ENDPOINT")
    if not endpoint:
        return
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if not _initialized:
        provider = TracerProvider(
            resource=Resource.create({"service.name": "ironclad"})
        )
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint))
        )
        trace.set_tracer_provider(provider)
        _initialized = True
    parent = trace.NonRecordingSpan(
        trace.SpanContext(
            trace_id=int(event.run_id, 16),
            span_id=1,
            is_remote=False,
            trace_flags=trace.TraceFlags(1),
        )
    )
    end = time.time_ns()
    span = trace.get_tracer("ironclad.agents").start_span(
        event.agent,
        context=trace.set_span_in_context(parent),
        start_time=end - event.duration_ms * 1000000,
        attributes={
            "run.id": event.run_id,
            "agent": event.agent,
            "event.seq": event.seq,
            "event.kind": event.kind,
        },
    )
    span.end(end_time=end)
