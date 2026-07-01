from __future__ import annotations

import pytest

from physical_agent.drivers.transport import (
    LoopbackTransport,
    TransportClosedError,
    TransportTimeoutError,
)


def test_loopback_transport_open_write_read_and_health():
    transport = LoopbackTransport()
    assert transport.health().status == "closed"

    transport.open()
    health = transport.health()
    assert health.ok is True
    assert health.status == "open"

    transport.write(b"hello")
    assert transport.drain_written() == b"hello"
    assert transport.drain_written() == b""

    transport.inject_read_data(b"world")
    assert transport.read(timeout_s=0.05) == b"world"

    transport.close()
    assert transport.health().status == "closed"


def test_loopback_transport_read_timeout_is_clear():
    transport = LoopbackTransport()
    transport.open()

    with pytest.raises(TransportTimeoutError, match="Loopback read timed out"):
        transport.read(timeout_s=0.01)

    health = transport.health()
    assert health.ok is True
    assert health.status == "open"
    assert "timed out" in health.details["last_error"]


def test_loopback_transport_closed_state_rejects_io():
    transport = LoopbackTransport()

    with pytest.raises(TransportClosedError, match="not open"):
        transport.write(b"closed")
    with pytest.raises(TransportClosedError, match="not open"):
        transport.read(timeout_s=0)
    with pytest.raises(TransportClosedError, match="not open"):
        transport.inject_read_data(b"closed")

    transport.open()
    transport.write(b"before-close")
    transport.close()

    with pytest.raises(TransportClosedError, match="not open"):
        transport.write(b"after-close")
    assert transport.drain_written() == b"before-close"
