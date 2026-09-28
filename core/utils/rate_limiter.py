from __future__ import annotations
import asyncio
import time
from collections import defaultdict
from typing import Dict


class TokenBucket:
    def __init__(self, rate_per_minute: int):
        self.capacity = max(1, rate_per_minute)
        self.tokens = float(self.capacity)
        self.refill_per_sec = rate_per_minute / 60.0
        self.last = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self.lock:
            now = time.monotonic()
            delta = now - self.last
            self.tokens = min(self.capacity, self.tokens + delta * self.refill_per_sec)
            self.last = now
            if self.tokens < 1:
                wait = (1 - self.tokens) / self.refill_per_sec
                await asyncio.sleep(wait)
                self.tokens = 0
            else:
                self.tokens -= 1


class PerHostRateLimiter:
    def __init__(self, default_rate: int = 30):
        self.default_rate = default_rate
        self.buckets: Dict[str, TokenBucket] = defaultdict(lambda: TokenBucket(default_rate))

    async def acquire(self, host: str) -> None:
        await self.buckets[host].acquire()


_global_limiter = PerHostRateLimiter()


def get_rate_limiter() -> PerHostRateLimiter:
    return _global_limiter
