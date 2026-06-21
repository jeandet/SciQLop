"""Standalone checks for the agent ``exec_python`` fix, run in a FRESH process.

Invoked as a subprocess by ``tests/test_agent_tools_off_gui_thread.py``. Creating a
real IPython kernel inside the shared pytest-qt session leaves residue that later
SIGSEGVs the GUI suite's ``load_all`` (see
``pitfall-agent-tools-block-gui-thread`` / ``pitfall-asyncio-run-main-thread-segfault``).
A separate interpreter has its own memory, so it cannot pollute the parent process.

Exits 0 and prints ``ALL OK`` if every check passes; otherwise prints the failure
to stderr and exits 1.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time


def _require(name: str, ok: bool) -> None:
    if not ok:
        print(f"FAIL: {name}", file=sys.stderr)
        sys.exit(1)
    print(f"ok: {name}")


def main() -> None:
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])

    from SciQLop.components.jupyter.kernel.manager import KernelManager

    km = KernelManager()
    km.start()
    try:
        caller = threading.current_thread().ident
        km.submit_cell(
            "import threading as _t; _tid = _t.current_thread().ident"
        ).result(timeout=10)
        _require("cell runs off the caller thread", km.shell.user_ns["_tid"] != caller)

        out = km.submit_cell("print('hello agent')").result(timeout=10)
        _require("captures stdout", "hello agent" in out["stdout"])

        err = km.submit_cell("1/0").result(timeout=10)
        _require(
            "reports errors",
            err["success"] is False and "ZeroDivisionError" in (err["error"] or ""),
        )

        _require("blocking cell keeps the awaiting loop responsive", _loop_stays_live(km))
    finally:
        km.shutdown()

    _require("thread-tagged tool runs off the event loop thread", _thread_tool_off_loop())
    print("ALL OK")


def _thread_tool_off_loop() -> bool:
    """A ``thread=True`` tool must run its callable off the event-loop thread."""
    from SciQLop.components.agents.tools import _builder

    seen: dict = {}

    def body(_payload):
        seen["tid"] = threading.current_thread().ident
        return "done"

    tool = _builder._text_tool(
        "t", "d", {"type": "object", "properties": {}, "required": []}, body, thread=True
    )

    async def drive():
        return await tool["handler"]({})

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(drive())
    finally:
        loop.close()
    return seen.get("tid") != threading.current_thread().ident and result["content"][0]["text"] == "done"


def _loop_stays_live(km) -> bool:
    """A cell that blocks ~0.8s must not stop the awaiting loop from ticking.

    The awaiting loop runs on its own thread with a private event loop, never the
    main thread's.
    """
    captured: dict = {}

    def run_private_loop() -> None:
        loop = asyncio.new_event_loop()
        try:
            captured["ticks"] = loop.run_until_complete(_scenario(km))
        finally:
            loop.close()

    worker = threading.Thread(target=run_private_loop)
    worker.start()
    worker.join(timeout=15)
    return bool(captured.get("ticks")) and len(captured["ticks"]) >= 5


async def _scenario(km) -> list:
    ticks: list = []

    async def ticker() -> None:
        for _ in range(8):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    cell = asyncio.wrap_future(km.submit_cell("import time; time.sleep(0.8)"))
    await asyncio.gather(cell, ticker())
    return ticks


if __name__ == "__main__":
    main()
