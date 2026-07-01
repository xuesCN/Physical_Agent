from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

from physical_agent.drivers.transport.base import (
    TransportClosedError,
    TransportError,
    TransportHealth,
    TransportTimeoutError,
)


_INSTALL_HINT = 'Install with pip install -e ".[serial]"'


class SerialTransport:
    """PySerial-backed byte transport for watch-side drivers."""

    def __init__(
        self,
        *,
        port: str,
        baudrate: int = 115200,
        timeout_s: float = 1.0,
        write_timeout_s: float | None = None,
        serial_module: Any | None = None,
    ) -> None:
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout_s = float(timeout_s)
        self.write_timeout_s = (
            None if write_timeout_s is None else float(write_timeout_s)
        )
        self._serial_module = serial_module if serial_module is not None else _import_pyserial()
        self._serial: Any | None = None
        self._last_error: str | None = None

    @property
    def is_open(self) -> bool:
        conn = self._serial
        return conn is not None and bool(getattr(conn, "is_open", True))

    def open(self) -> None:
        self.close()
        self._last_error = None
        try:
            self._serial = self._serial_module.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout_s,
                write_timeout=self.write_timeout_s,
            )
        except _serial_exception_types(self._serial_module) as exc:
            self._last_error = f"Serial connection failed: {exc}"
            raise TransportError(self._last_error) from exc
        except (OSError, ValueError) as exc:
            self._last_error = f"Serial connection failed: {exc}"
            raise TransportError(self._last_error) from exc

    def close(self) -> None:
        conn = self._serial
        self._serial = None
        if conn is None:
            return
        try:
            conn.close()
        except _serial_exception_types(self._serial_module) as exc:
            self._last_error = f"Serial close failed: {exc}"
        except OSError as exc:
            self._last_error = f"Serial close failed: {exc}"

    def write(self, data: bytes) -> None:
        payload = bytes(data)
        conn = self._require_serial()
        written: int | None = None
        try:
            written = conn.write(payload)
            flush = getattr(conn, "flush", None)
            if callable(flush):
                flush()
        except _serial_timeout_types(self._serial_module) as exc:
            self._last_error = "Serial write timed out"
            raise TransportTimeoutError(self._last_error) from exc
        except _serial_exception_types(self._serial_module) as exc:
            self._last_error = f"Serial write failed: {exc}"
            raise TransportError(self._last_error) from exc
        except OSError as exc:
            self._last_error = f"Serial write failed: {exc}"
            raise TransportError(self._last_error) from exc
        if written is not None and int(written) < len(payload):
            self._last_error = "Serial write timed out before all bytes were written"
            raise TransportTimeoutError(self._last_error)

    def read(self, timeout_s: float) -> bytes:
        conn = self._require_serial()
        previous_timeout = getattr(conn, "timeout", None)
        can_restore_timeout = hasattr(conn, "timeout")
        try:
            if can_restore_timeout:
                conn.timeout = float(timeout_s)
            available = int(getattr(conn, "in_waiting", 0) or 0)
            size = max(1, available)
            data = bytes(conn.read(size))
        except _serial_timeout_types(self._serial_module) as exc:
            self._last_error = "Serial read timed out"
            raise TransportTimeoutError(self._last_error) from exc
        except _serial_exception_types(self._serial_module) as exc:
            self._last_error = f"Serial read failed: {exc}"
            raise TransportError(self._last_error) from exc
        except OSError as exc:
            self._last_error = f"Serial read failed: {exc}"
            raise TransportError(self._last_error) from exc
        finally:
            if can_restore_timeout and self._serial is conn:
                conn.timeout = previous_timeout

        if not data:
            self._last_error = f"Serial read timed out after {float(timeout_s):g}s"
            raise TransportTimeoutError(self._last_error)
        return data

    def health(self) -> TransportHealth:
        if self.is_open:
            return TransportHealth(
                ok=True,
                status="open",
                message="Serial transport open",
                details={
                    "port": self.port,
                    "baudrate": self.baudrate,
                    "timeout_s": self.timeout_s,
                    "write_timeout_s": self.write_timeout_s,
                    "last_error": self._last_error,
                },
            )
        if self._last_error:
            return TransportHealth(
                ok=False,
                status="error",
                message=self._last_error,
                details={"port": self.port, "baudrate": self.baudrate},
            )
        return TransportHealth(
            ok=False,
            status="closed",
            message="Serial transport closed",
            details={"port": self.port, "baudrate": self.baudrate},
        )

    def _require_serial(self) -> Any:
        conn = self._serial
        if conn is None or not bool(getattr(conn, "is_open", True)):
            self._serial = None
            raise TransportClosedError("Serial transport is not open")
        return conn


def _import_pyserial() -> ModuleType:
    try:
        return importlib.import_module("serial")
    except ModuleNotFoundError as exc:
        raise TransportError(f"pyserial is required for SerialTransport. {_INSTALL_HINT}") from exc


def _serial_exception_types(serial_module: Any) -> tuple[type[BaseException], ...]:
    serial_exception = getattr(serial_module, "SerialException", None)
    if isinstance(serial_exception, type) and issubclass(serial_exception, BaseException):
        return (serial_exception,)
    return ()


def _serial_timeout_types(serial_module: Any) -> tuple[type[BaseException], ...]:
    timeout_exception = getattr(serial_module, "SerialTimeoutException", None)
    if isinstance(timeout_exception, type) and issubclass(timeout_exception, BaseException):
        return (timeout_exception,)
    return ()
