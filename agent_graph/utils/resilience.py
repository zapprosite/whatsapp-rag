from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

ResultT = TypeVar("ResultT")


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    pass


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 4
    recovery_timeout_seconds: float = 45.0
    half_open_success_threshold: int = 1


class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_success_count = 0
        self._opened_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state != CircuitState.OPEN:
                return

            elapsed = time.monotonic() - self._opened_at
            if elapsed >= self.config.recovery_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_success_count = 0
                return

            wait = self.config.recovery_timeout_seconds - elapsed
            raise CircuitOpenError(f"Circuito {self.name} aberto; retry em {wait:.1f}s")

    async def _record_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_success_count += 1
                if self._half_open_success_count < self.config.half_open_success_threshold:
                    return
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_success_count = 0

    async def _record_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.config.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                self._half_open_success_count = 0

    async def call(self, fn: Callable[[], Awaitable[ResultT]]) -> ResultT:
        await self._before_call()
        try:
            result = await fn()
        except Exception:
            await self._record_failure()
            raise
        await self._record_success()
        return result


async def sleep_with_backoff(
    attempt: int,
    *,
    base_seconds: float = 0.75,
    cap_seconds: float = 12.0,
) -> None:
    delay = min(cap_seconds, base_seconds * (2**attempt))
    await asyncio.sleep(random.uniform(0.0, delay))

