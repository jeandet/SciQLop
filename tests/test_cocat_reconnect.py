"""The cocat client must reconnect automatically after a dropped connection,
and stop cleanly on leave. We drive Client._run with a fake session (no real
websocket) so the loop logic is exercised deterministically.
"""
import asyncio

import pytest

pytest.importorskip("cocat")
pytest.importorskip("wire_websocket")


def _make_client(monkeypatch, fake_session):
    from SciQLop.plugins.collaborative_catalogs import client as client_mod
    monkeypatch.setattr(client_mod, "_RECONNECT_INITIAL_BACKOFF", 0.01)
    monkeypatch.setattr(client_mod, "_RECONNECT_MAX_BACKOFF", 0.01)
    monkeypatch.setattr(client_mod, "_ensure_logged_in", lambda self: True)
    c = client_mod.Client(url="https://h/", room_id="r")
    monkeypatch.setattr(c, "_connect_session", fake_session)
    return c


def test_run_reconnects_after_drops_then_stops_on_close(qapp, monkeypatch):
    attempts = {"n": 0}

    async def fake_session():
        attempts["n"] += 1
        c._connected = True
        c._ever_connected = True
        c._connecting_event.set()
        if attempts["n"] < 3:          # first two sessions drop
            c._connected = False
            raise RuntimeError("dropped")
        await c._close_event.wait()    # third session stays up until close
        c._connected = False

    c = _make_client(monkeypatch, fake_session)

    async def drive():
        c._connecting_event.clear()
        c._close_event.clear()
        c._ever_connected = False
        task = asyncio.create_task(c._run())
        for _ in range(500):
            if attempts["n"] >= 3 and c._connected:
                break
            await asyncio.sleep(0.005)
        c._close_event.set()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(drive())
    assert attempts["n"] >= 3          # retried after each drop until stable
    assert c._connected is False       # cleanly torn down after close


def test_run_gives_up_when_initial_connection_never_succeeds(qapp, monkeypatch):
    attempts = {"n": 0}

    async def fake_session():
        attempts["n"] += 1
        # never sets _ever_connected: simulate a connection that fails to establish
        raise RuntimeError("cannot connect")

    c = _make_client(monkeypatch, fake_session)

    async def drive():
        c._connecting_event.clear()
        c._close_event.clear()
        c._ever_connected = False
        task = asyncio.create_task(c._run())
        await asyncio.wait_for(task, timeout=2.0)   # must terminate, not retry forever

    asyncio.run(drive())
    assert attempts["n"] == 1           # no retry of a never-established connection
    assert c._connected is False
