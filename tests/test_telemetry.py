import pytest

from ironclad.schema import Agent, Message


def test_agent_span_uses_run_trace_id(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from ironclad import telemetry

    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setenv("IRONCLAD_OTLP_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
    monkeypatch.setattr(telemetry, "_initialized", True)
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    rid = "0123456789abcdef0123456789abcdef"
    telemetry.record(
        Message(
            run_id=rid,
            seq=1,
            agent=Agent.WATCHER,
            kind="incident",
            payload={},
            timestamp="2026-11-10T00:00:00Z",
            duration_ms=15,
        )
    )
    span = exporter.get_finished_spans()[0]
    assert span.context.trace_id == int(rid, 16)
    assert span.end_time - span.start_time == 15000000
    assert span.attributes["event.kind"] == "incident"
    provider.shutdown()
