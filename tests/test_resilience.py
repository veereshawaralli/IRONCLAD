import io
import urllib.error
from email.message import Message

import pytest

from ironclad.resilience import CircuitBreaker, ProviderError, request_with_backoff


def test_circuit_opens_and_recovers():
    now = [0.0]
    breaker = CircuitBreaker(2, 5, lambda: now[0])
    breaker.failed()
    breaker.failed()
    with pytest.raises(ProviderError, match="circuit_open"):
        breaker.check()
    now[0] = 6
    breaker.check()
    breaker.succeeded()
    breaker.check()


def test_http_retry_reserves_each_attempt(monkeypatch):
    from ironclad import resilience

    monkeypatch.setattr(resilience, "_model_circuit", CircuitBreaker())
    monkeypatch.setattr("time.sleep", lambda n: None)
    calls = []

    def request():
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                "https://provider.invalid", 429, "rate limited", Message(), io.BytesIO()
            )
        return "ok"

    assert request_with_backoff(request, lambda: calls.append(1)) == "ok"
    assert len(calls) == 2


def test_timeout_not_repeated(monkeypatch):
    from ironclad import resilience

    monkeypatch.setattr(resilience, "_model_circuit", CircuitBreaker())
    calls = []

    def request():
        raise TimeoutError()

    with pytest.raises(ProviderError, match="unknown"):
        request_with_backoff(request, lambda: calls.append(1))
    assert len(calls) == 1


def test_nonfinite_budget_rejected():
    from ironclad.schema import FleetPolicy

    with pytest.raises(ValueError):
        FleetPolicy(dollar_budget=float("inf"))
