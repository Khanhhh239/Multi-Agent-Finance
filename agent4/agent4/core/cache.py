"""Bounded process-local caching for governed pipeline stages."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from math import isfinite
from pathlib import Path
from sys import getsizeof
from threading import Lock
from time import monotonic
from typing import Any, Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


def build_scoped_cache_key(
    namespace: str, *, tenant_id: str, policy_hash: str, catalog_hash: str, **parts: Any
) -> str:
    """Hash a canonical JSON payload that includes the server-owned scope."""
    scope = (namespace, tenant_id, policy_hash, catalog_hash)
    if any(not isinstance(value, str) or not value.strip() for value in scope):
        raise ValueError("Cache namespace, tenant, policy and catalog are required.")
    payload = json.dumps([scope, parts], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_revision(path: Path) -> tuple[str, int, int, int, int, int]:
    """Identify a server-configured artifact without reading its contents."""
    path = path.absolute()
    info = path.stat()
    return (str(path), info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino, info.st_size)


def _estimated_size(value: Any, seen: set[int]) -> int:
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = getsizeof(value)
    buffer_size = getattr(value, "nbytes", 0)
    if isinstance(buffer_size, int):
        size = max(size, buffer_size)
    if isinstance(value, dict):
        return size + sum(
            _estimated_size(key, seen) + _estimated_size(item, seen) for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set, frozenset)):
        return size + sum(_estimated_size(item, seen) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "__dict__"):
            return size + _estimated_size(vars(value), seen)
        return size + sum(
            _estimated_size(getattr(value, field.name), seen) for field in fields(value)
        )
    return size


class LRUTTLCache(Generic[K, V]):
    """Limit resident entries by estimated bytes, rows, age and recency."""

    def __init__(
        self,
        *,
        max_entries: int,
        ttl_seconds: float,
        max_bytes_budget: int,
        max_rows_per_entry: int,
        clone_on_read: bool = True,
    ) -> None:
        if (
            max_entries < 1
            or max_bytes_budget < 1
            or max_rows_per_entry < 1
            or not isfinite(ttl_seconds)
            or ttl_seconds <= 0
        ):
            raise ValueError("Cache limits must be positive and TTL must be finite.")
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._max_bytes = max_bytes_budget
        self._max_rows = max_rows_per_entry
        self._clone = clone_on_read
        self._entries: OrderedDict[K, tuple[V, float, int]] = OrderedDict()
        self._lock = Lock()
        self._bytes = self._hits = self._misses = self._evictions = 0

    def get(self, key: K) -> V | None:
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[1] <= monotonic():
                self._remove(key, eviction=True)
                entry = None
            if entry is None:
                self._misses += 1
                return None
            self._entries.move_to_end(key)
            self._hits += 1
        return deepcopy(entry[0]) if self._clone else entry[0]

    def set(self, key: K, value: V, *, row_count: int | None = None) -> bool:
        """Store a snapshot if it fits. A rejected replacement invalidates the old entry."""
        rows = value.get("rows") if isinstance(value, Mapping) else value
        inferred = len(rows) if isinstance(rows, (list, tuple)) else 0
        if row_count is not None and (type(row_count) is not int or row_count < 0):
            raise ValueError("Row count must be a nonnegative integer.")
        fits = value is not None and max(inferred, row_count or 0) <= self._max_rows
        if fits:
            # Include the key, expiry, size field and per-entry OrderedDict bookkeeping.
            size = _estimated_size((key, value, 0.0, 0), set()) + 128
            fits = size <= self._max_bytes
        if fits:
            stored = deepcopy(value) if self._clone else value
            if self._clone:
                size = _estimated_size((key, stored, 0.0, 0), set()) + 128
                fits = size <= self._max_bytes

        with self._lock:
            now = monotonic()
            self._expire(now)
            if key in self._entries:
                self._remove(key)
            if not fits:
                return False
            while len(self._entries) >= self._max_entries or self._bytes + size > self._max_bytes:
                self._remove(next(iter(self._entries)), eviction=True)
            self._entries[key] = (stored, now + self._ttl, size)
            self._bytes += size
            return True

    def discard(self, key: K) -> None:
        with self._lock:
            if key in self._entries:
                self._remove(key)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            self._expire(monotonic())
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "active_entries": len(self._entries),
                "estimated_memory_kb": self._bytes / 1024,
            }

    def _expire(self, now: float) -> None:
        for key in [key for key, (_, deadline, _) in self._entries.items() if deadline <= now]:
            self._remove(key, eviction=True)

    def _remove(self, key: K, *, eviction: bool = False) -> None:
        _, _, size = self._entries.pop(key)
        self._bytes -= size
        self._evictions += int(eviction)
