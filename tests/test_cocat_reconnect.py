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


def test_run_does_not_block_loop_during_slow_login(qapp, monkeypatch):
    """login() does blocking HTTP; _run must keep it off the event loop or the
    UI freezes for the full HTTP timeout on every reconnect attempt (P3)."""
    import time as _time
    from SciQLop.plugins.collaborative_catalogs import client as client_mod

    def slow_login(self):
        _time.sleep(0.3)
        return False  # never logs in -> _run exits after one iteration

    async def fake_session():
        raise AssertionError("should not connect")

    c = _make_client(monkeypatch, fake_session)
    monkeypatch.setattr(client_mod, "_ensure_logged_in", slow_login)

    async def drive():
        loop = asyncio.get_running_loop()
        gaps = []

        async def ticker():
            last = loop.time()
            while True:
                await asyncio.sleep(0.01)
                now = loop.time()
                gaps.append(now - last)
                last = now

        t = asyncio.create_task(ticker())
        await asyncio.sleep(0.05)        # let the ticker establish its baseline
        c._connecting_event.clear()
        c._close_event.clear()
        c._ever_connected = False
        await asyncio.wait_for(c._run(), timeout=2.0)
        await asyncio.sleep(0.05)        # let the post-block tick get recorded
        t.cancel()
        return max(gaps) if gaps else 0.0

    worst_stall = asyncio.run(drive())
    assert worst_stall < 0.2, \
        f"event loop stalled {worst_stall:.3f}s during login — must run in a thread"


def test_join_room_during_backoff_does_not_leak_previous_loop(qapp, monkeypatch):
    """Reproducer (2026-06-09 review): join_room guarded re-join with
    `if self._connected`, which is False while the old _run loop sleeps in
    reconnect backoff — so a second _run loop was spawned and both ended up
    holding sessions concurrently."""
    from SciQLop.plugins.collaborative_catalogs import client as client_mod

    state = {"attempts": 0, "active": 0, "max_active": 0}

    async def fake_session():
        state["attempts"] += 1
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        try:
            c._connected = True
            c._ever_connected = True
            c._connecting_event.set()
            if state["attempts"] == 1:    # first session drops -> backoff
                c._connected = False
                raise RuntimeError("dropped")
            await c._close_event.wait()
            c._connected = False
        finally:
            state["active"] -= 1

    c = _make_client(monkeypatch, fake_session)
    monkeypatch.setattr(client_mod, "_RECONNECT_INITIAL_BACKOFF", 0.5)
    monkeypatch.setattr(client_mod, "_RECONNECT_MAX_BACKOFF", 0.5)

    async def drive():
        await c.join_room("r")            # first session drops; loop enters backoff
        await asyncio.sleep(0.1)
        assert c._task is not None and not c._connected   # in backoff

        await c.join_room("r2")           # re-join while old loop is backing off
        for _ in range(200):
            if c._connected:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.7)          # let a leaked old loop wake up, if any
        await c.leave_room()

    asyncio.run(drive())
    assert state["max_active"] == 1, \
        "re-joining during backoff must stop the previous loop, not run two sessions"


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
