"""Seed certificate: token bucket rate limiter."""

import time
from certus.decorator import certus


class TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()

    @certus(
        preconditions=[],
        postconditions=[
            {"when": "always", "guarantees": ["0 <= self.tokens <= self.capacity"]},
        ],
        effects={"reads": ["self.rate", "self.capacity"], "mutates": ["self.tokens", "self.last_refill"]},
        object_invariants=["0 <= self.tokens <= self.capacity", "self.rate > 0"],
        assumptions=["time.monotonic() is non-decreasing"],
    )
    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

    @certus(
        preconditions=["n >= 1"],
        postconditions=[
            {"when": "result is True", "guarantees": ["self.tokens >= 0"]},
            {"when": "result is False", "guarantees": ["self.tokens >= 0", "self.tokens < n"]},
        ],
        effects={"reads": ["self.rate", "self.capacity"], "mutates": ["self.tokens", "self.last_refill"]},
        object_invariants=["0 <= self.tokens <= self.capacity", "self.rate > 0"],
        depends_on=[
            {"function": "TokenBucket._refill", "certified": True, "uses": ["0 <= self.tokens <= self.capacity"]},
        ],
    )
    def consume(self, n: int = 1) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False
