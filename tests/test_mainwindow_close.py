"""closeEvent must not assume a usable asyncio loop (2026-06-09 review).

At pytest session teardown the current loop is absent or never ran;
`asyncio.ensure_future` then raised out of closeEvent, leaving the window
half-closed and erroring the last test's teardown.
"""
import asyncio

from .fixtures import *


def _restore_loop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return None


def test_usable_event_loop_guards(qapp):
    from SciQLop.core.ui.mainwindow import SciQLopMainWindow
    prev = _restore_loop()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        assert SciQLopMainWindow._usable_event_loop() is None, \
            "a loop that is not running cannot execute _async_close"
        loop.close()
        assert SciQLopMainWindow._usable_event_loop() is None
        asyncio.set_event_loop(None)
        assert SciQLopMainWindow._usable_event_loop() is None
    finally:
        asyncio.set_event_loop(prev)


def test_usable_event_loop_detects_running_loop(qapp):
    from SciQLop.core.ui.mainwindow import SciQLopMainWindow
    prev = _restore_loop()

    async def probe():
        return SciQLopMainWindow._usable_event_loop()

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        assert loop.run_until_complete(probe()) is loop
        loop.close()
    finally:
        asyncio.set_event_loop(prev)
