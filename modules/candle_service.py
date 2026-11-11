"""Centralized candle snapshots with a small, entitlement-aware TTL cache.

The cache stores complete normalized snapshots, not provider SDK objects. A hit
therefore preserves the original snapshot ID and retrieval timestamp. TTL expiry
is the only automatic invalidation; callers never bypass the cache.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock

from modules.data_entitlements import PRIVATE_RESEARCH, enforce_data_use
from modules.market_data_gateway import (
    MarketDataProvider,
    PublicMarketDataProvider,
    build_snapshot,
    validate_candle_request,
)


class CandleSnapshotCache:
    """Bounded process-local cache whose reads re-check data-use permission."""

    def __init__(self, clock, *, ttl_seconds: int = 20, maxsize: int = 16):
        if not 15 <= int(ttl_seconds) <= 30:
            raise ValueError("Candle cache TTL must be between 15 and 30 seconds.")
        self.clock = clock
        self.ttl_seconds = int(ttl_seconds)
        self.maxsize = int(maxsize)
        self._items: OrderedDict = OrderedDict()
        self._lock = RLock()

    def get(self, key, use_context: str = PRIVATE_RESEARCH):
        now = self.clock().timestamp()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            expires_at, snapshot = entry
            if now >= expires_at:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            # Re-check the policy on every cache read. A cached Public snapshot
            # must never become public-display data merely because it was cached
            # while private research was allowed.
            enforce_data_use(use_context, snapshot.provider)
            return deepcopy(snapshot)

    def put(self, key, snapshot, use_context: str = PRIVATE_RESEARCH) -> None:
        enforce_data_use(use_context, snapshot.provider)
        now = self.clock().timestamp()
        with self._lock:
            for old_key, (expires_at, _) in list(self._items.items()):
                if expires_at <= now:
                    del self._items[old_key]
            self._items[key] = (now + self.ttl_seconds, deepcopy(snapshot))
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)


class CandleService:
    """Resolve provider-native candles and build stable, cacheable snapshots."""

    def __init__(self, provider: MarketDataProvider | None = None, *,
                 clock=None, ttl_seconds: int = 20, maxsize: int = 16):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.provider = provider or PublicMarketDataProvider(clock=self.clock)
        self.cache = CandleSnapshotCache(
            self.clock, ttl_seconds=ttl_seconds, maxsize=maxsize)

    def get(self, symbol: str, interval: str = "1m", session: str = "regular",
            limit: int = 390, use_context: str = PRIVATE_RESEARCH):
        # Fail before a provider call or cache lookup when the requested use is
        # not entitled. The provider may have a different identity than the
        # service's configured provider, so build_snapshot checks it again.
        enforce_data_use(use_context, self.provider.name)
        normalized_symbol = validate_candle_request(symbol, interval, session, limit)
        key = (self.provider.name, normalized_symbol, interval, session, limit)
        cached = self.cache.get(key, use_context)
        if cached is not None:
            return cached
        batch = self.provider.candles(normalized_symbol, interval, session, limit)
        decision = enforce_data_use(use_context, batch.provider)
        snapshot = build_snapshot(batch, now=self.clock(), entitlement=decision)
        self.cache.put(key, snapshot, use_context)
        return snapshot

    def capabilities(self) -> dict:
        return self.provider.capabilities.as_dict()
