"""Redacted failures and bounded provider backoff; uncertain POSTs are not retried."""

import math
import threading
import time
import urllib.error
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class ProviderError(ValueError):
    def __init__(self, kind: str, retryable: bool = False):
        self.kind = kind
        self.retryable = retryable
        super().__init__("Provider failure: " + kind)


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,
        cooldown: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.failures = 0
        self.until = 0.0
        self.lock = threading.Lock()

    def check(self) -> None:
        with self.lock:
            if self.clock() < self.until:
                raise ProviderError("circuit_open", True)

    def failed(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= self.threshold:
                self.until = self.clock() + self.cooldown

    def succeeded(self) -> None:
        with self.lock:
            self.failures = 0
            self.until = 0.0


_model_circuit = CircuitBreaker()


def request_with_backoff[T](
    operation: Callable[[], T], reserve: Callable[[], None]
) -> T:
    for attempt in range(3):
        _model_circuit.check()
        reserve()
        try:
            value = operation()
            _model_circuit.succeeded()
            return value
        except urllib.error.HTTPError as exc:
            _model_circuit.failed()
            retryable = exc.code in {429, 502, 503, 504}
            if not retryable or attempt == 2:
                raise ProviderError("http_" + str(exc.code), retryable) from None
            try:
                delay = float(exc.headers.get("Retry-After", "0"))
            except (ValueError, AttributeError):
                delay = 0
            if not math.isfinite(delay) or delay > 5:
                raise ProviderError("rate_limited", True) from None
            time.sleep(max(delay, 0.2 * (2**attempt)))
        except (TimeoutError, urllib.error.URLError):
            _model_circuit.failed()
            # Unknown outcome: a repeat might create another billed request.
            raise ProviderError("network_outcome_unknown", True) from None
    raise ProviderError("request_exhausted")
