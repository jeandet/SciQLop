"""Per-graph main-side state machine driving one SciQLopPlots remote channel.

Owns req_id assignment, stale-reply dropping, and the consumer-side segment
lifetime: the previous segment is FREEd only once a newer set_data supersedes
it (so SciQLopPlots never reads a buffer the worker might overwrite)."""
from __future__ import annotations

import logging
from multiprocessing import shared_memory
from typing import Optional

from .protocol import unpack_arrays

log = logging.getLogger(__name__)


class RemoteChannel:
    def __init__(self, pipeline, channel_id: int, transport):
        self._pipeline = pipeline
        self.channel_id = channel_id
        self._transport = transport
        self._latest_req_id = 0
        self._held: Optional[shared_memory.SharedMemory] = None
        self._held_name: Optional[str] = None
        self._knobs: dict = {}

    # --- outgoing -----------------------------------------------------------
    def set_knobs(self, knobs: dict) -> None:
        self._knobs = dict(knobs)

    def on_data_requested_values(self, start: float, stop: float) -> None:
        self._latest_req_id += 1
        self._transport.send_request(self.channel_id, self._latest_req_id, start, stop, self._knobs)

    def on_data_requested(self, rng) -> None:
        self.on_data_requested_values(rng.start(), rng.stop())

    # --- incoming -----------------------------------------------------------
    def on_result(self, req_id: int, shm_name: str, layout, arity: int) -> None:
        if req_id < self._latest_req_id:
            self._transport.send_free(self.channel_id, shm_name)   # stale: drop + free
            return
        shm = shared_memory.SharedMemory(name=shm_name, create=False, track=False)
        views = unpack_arrays(shm.buf, layout)
        self._pipeline.set_data(*views)
        self._supersede(shm, shm_name)

    def on_empty(self, req_id: int) -> None:
        pass

    def on_error(self, req_id: int, tb: str) -> None:
        log.error("remote data source error (channel %s):\n%s", self.channel_id, tb)

    # --- lifetime -----------------------------------------------------------
    def _supersede(self, shm, name) -> None:
        prev, prev_name = self._held, self._held_name
        self._held, self._held_name = shm, name
        if prev is not None:
            prev.close()
            if prev_name != name:   # never FREE the segment we still hold live
                self._transport.send_free(self.channel_id, prev_name)

    def dispose(self) -> None:
        self._transport.release(self.channel_id)
        if self._held is not None:
            self._held.close()
            self._transport.send_free(self.channel_id, self._held_name)
            self._held, self._held_name = None, None
