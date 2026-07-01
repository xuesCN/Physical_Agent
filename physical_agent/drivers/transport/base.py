from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TransportHealth:
    ok: bool
    status: str
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


class TransportError(RuntimeError):
    """Base error raised by watch-side byte transports."""


class TransportTimeoutError(TimeoutError, TransportError):
    """Raised when a transport operation exceeds its timeout."""


class TransportClosedError(TransportError):
    """Raised when the peer closes before an operation can complete."""


class TransportProtocolError(TransportError):
    """Raised when the peer violates the expected transport protocol."""


@runtime_checkable
class Transport(Protocol):
    """Byte transport owned by watch-side drivers."""

    def open(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read(self, timeout_s: float) -> bytes:
        raise NotImplementedError

    def health(self) -> TransportHealth:
        raise NotImplementedError
