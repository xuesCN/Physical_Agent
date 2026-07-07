from __future__ import annotations

import pytest

from physical_agent.drivers.transport import (
    LoopbackTransport,
    ReconnectPolicy,
    TransportClosedError,
    TransportReconnectFailed,
    TransportReconnecting,
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


def test_loopback_reconnect_policy_retries_connect_with_backoff():
    sleeps: list[float] = []
    transport = LoopbackTransport(
        reconnect_policy=ReconnectPolicy(
            enabled=True,
            max_retries=2,
            backoff_base_ms=10,
            backoff_cap_ms=100,
        ),
        reconnect_sleeper=sleeps.append,
        fail_connect_attempts=2,
    )

    transport.open()

    assert transport.is_open is True
    assert transport.connection_state == "connected"
    assert transport.open_attempts == 3
    assert sleeps == [0.01, 0.02]


def test_loopback_reconnect_policy_exhausts_max_retries():
    transport = LoopbackTransport(
        reconnect_policy={
            "enabled": True,
            "max_retries": 1,
            "backoff_base_ms": 10,
            "backoff_cap_ms": 10,
        },
        reconnect_sleeper=lambda _delay: None,
        fail_connect_attempts=99,
    )

    with pytest.raises(TransportReconnectFailed, match="failed after 2 attempt"):
        transport.open()

    assert transport.is_open is False
    assert transport.open_attempts == 2
    assert transport.connection_state == "disconnected"


def test_loopback_reconnecting_write_fails_fast_without_queueing():
    transport = LoopbackTransport(
        reconnect_policy=ReconnectPolicy(
            enabled=True,
            max_retries=1,
            backoff_base_ms=100,
            backoff_cap_ms=100,
        )
    )
    transport.open()
    transport.set_fail_connect_attempts(99)
    transport.simulate_disconnect(start_reconnect=True)

    with pytest.raises(TransportReconnecting, match="not queued"):
        transport.write(b"must-not-queue")

    assert transport.drain_written() == b""
    transport.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_retries": -1},
        {"backoff_base_ms": 0},
        {"backoff_base_ms": 50, "backoff_cap_ms": 10},
        {"jitter_ms": -1},
    ],
)
def test_reconnect_policy_validation(kwargs):
    with pytest.raises(ValueError):
        ReconnectPolicy(**kwargs)
