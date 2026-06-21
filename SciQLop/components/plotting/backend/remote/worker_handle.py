"""Main-side handle on one worker subprocess.

Spawns the worker, owns the duplex Connection, and pumps replies onto the main
thread via a QSocketNotifier on the connection's fd. Implements the transport
interface (send_request/send_free/release) that RemoteChannel calls."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from multiprocessing.connection import Listener
from typing import Dict

from PySide6.QtCore import QObject, QSocketNotifier

from . import protocol as P

log = logging.getLogger(__name__)


class RemoteWorker(QObject):
    def __init__(self, plugin_key: str, parent: QObject | None = None):
        super().__init__(parent)
        self.plugin_key = plugin_key
        self._proc: subprocess.Popen | None = None
        self._conn = None
        self._notifier: QSocketNotifier | None = None
        self._channels: Dict[int, object] = {}

    # --- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._proc is not None:
            return
        authkey = os.urandom(32)
        address = os.path.join(tempfile.gettempdir(), f"sciqlop-remote-{os.getpid()}-{id(self)}")
        listener = Listener(address, authkey=authkey)
        self._proc = subprocess.Popen(
            [sys.executable, "-m",
             "SciQLop.components.plotting.backend.remote.worker", address],
            stdin=subprocess.PIPE,
        )
        self._proc.stdin.write(authkey)
        self._proc.stdin.close()
        self._conn = listener.accept()
        listener.close()
        self._notifier = QSocketNotifier(self._conn.fileno(), QSocketNotifier.Type.Read)
        self._notifier.activated.connect(self._on_readable)

    def shutdown(self) -> None:
        try:
            if self._conn is not None:
                self._conn.send((P.SHUTDOWN,))
        except Exception:
            pass
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        if self._proc is not None:
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc, self._conn, self._notifier = None, None, None

    # --- channels -----------------------------------------------------------
    def register_channel(self, channel) -> None:
        self._channels[channel.channel_id] = channel

    def install(self, channel_id: int, blob: bytes, arity: int) -> None:
        self._conn.send((P.INSTALL, channel_id, blob, arity))

    # --- transport interface (called by RemoteChannel) ----------------------
    def send_request(self, channel_id: int, req_id: int, start: float, stop: float) -> None:
        self._conn.send((P.REQUEST, channel_id, req_id, start, stop))

    def send_free(self, channel_id: int, name: str) -> None:
        self._conn.send((P.FREE, channel_id, name))

    def release(self, channel_id: int) -> None:
        self._channels.pop(channel_id, None)
        if self._conn is not None:
            try:
                self._conn.send((P.RELEASE, channel_id))
            except Exception:
                pass

    # --- reply pump ---------------------------------------------------------
    def _on_readable(self) -> None:
        while self._conn is not None and self._conn.poll(0):
            try:
                msg = self._conn.recv()
            except EOFError:
                self._on_worker_died()
                return
            self._dispatch(msg)

    def _dispatch(self, msg) -> None:
        tag = msg[0]
        if tag == P.RESULT:
            _, ch, req, name, layout, arity = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_result(req, name, layout, arity)
        elif tag == P.EMPTY:
            _, ch, req = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_empty(req)
        elif tag == P.ERROR:
            _, ch, req, tb = msg
            c = self._channels.get(ch)
            if c is not None:
                c.on_error(req, tb)

    def _on_worker_died(self) -> None:
        log.warning("remote worker for %s died", self.plugin_key)
        if self._notifier is not None:
            self._notifier.setEnabled(False)
        self._proc, self._conn, self._notifier = None, None, None
