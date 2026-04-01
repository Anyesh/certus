"""Seed certificate: bounded stack."""

from certus.decorator import certus


class BoundedStack:
    def __init__(self, max_size: int):
        self.max_size = max_size
        self._items: list = []

    @certus(
        preconditions=["len(self._items) < self.max_size"],
        postconditions=[{"when": "always", "guarantees": ["len(self._items) <= self.max_size"]}],
        effects={"reads": ["self.max_size"], "mutates": ["self._items"]},
        object_invariants=["len(self._items) <= self.max_size"],
    )
    def push(self, item) -> None:
        self._items.append(item)

    @certus(
        preconditions=["len(self._items) > 0"],
        postconditions=[{"when": "always", "guarantees": ["len(self._items) <= self.max_size"]}],
        effects={"reads": [], "mutates": ["self._items"]},
        object_invariants=["len(self._items) <= self.max_size"],
    )
    def pop(self):
        return self._items.pop()
