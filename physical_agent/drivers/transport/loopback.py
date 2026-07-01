from __future__ import annotations

import threading
import time

from physical_agent.drivers.transport.base import (
    TransportClosedError,
    TransportHealth,
    TransportTimeoutError,
)


class LoopbackTransport:
    """In-memory byte transport for watch-side tests and local simulations."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._is_open = False
        self._read_buffer = bytearray()
        self._written_buffer = bytearray()
        self._last_error: str | None = None

    @property
    def is_open(self) -> bool:
        return self._is_open

    def open(self) -> None:
        with self._condition:
            self._is_open = True
            self._last_error = None
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._is_open = False
            self._read_buffer.clear()
            self._condition.notify_all()

    def write(self, data: bytes) -> None:
        payload = bytes(data)
        with self._condition:
            self._require_open_locked()
            self._written_buffer.extend(payload)

    def read(self, timeout_s: float) -> bytes:
        timeout = max(0.0, float(timeout_s))
        deadline = time.monotonic() + timeout
        with self._condition:
            self._require_open_locked()
            while not self._read_buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._last_error = f"Loopback read timed out after {timeout:g}s"
                    raise TransportTimeoutError(self._last_error)
                self._condition.wait(timeout=remaining)
                self._require_open_locked()

            payload = bytes(self._read_buffer)
            self._read_buffer.clear()
            return payload

    def inject_read_data(self, data: bytes) -> None:
        payload = bytes(data)
        with self._condition:
            self._require_open_locked()
            self._read_buffer.extend(payload)
            self._condition.notify_all()

    def drain_written(self) -> bytes:
        with self._condition:
            payload = bytes(self._written_buffer)
            self._written_buffer.clear()
            return payload

    def health(self) -> TransportHealth:
        with self._condition:
            if self._is_open:
                return TransportHealth(
                    ok=True,
                    status="open",
                    message="Loopback transport open",
                    details={
                        "read_buffer_bytes": len(self._read_buffer),
                        "written_buffer_bytes": len(self._written_buffer),
                        "last_error": self._last_error,
                    },
                )
            return TransportHealth(
                ok=False,
                status="closed",
                message="Loopback transport closed",
                details={"last_error": self._last_error},
            )

    def _require_open_locked(self) -> None:
        if not self._is_open:
            raise TransportClosedError("Loopback transport is not open")
