"""Per-channel shared-memory segment pool, owned by the worker process.

The worker is the SOLE creator and unlinker of segments (track=False so the
resource_tracker never touches them). A segment handed out by acquire() is
'in use' until mark_reusable() returns it — the consumer drives that via FREE
messages once a newer set_data supersedes the buffer. This is what makes the
zero-copy hand-off race-free."""
from __future__ import annotations

import os
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Dict


@dataclass
class Segment:
    shm: shared_memory.SharedMemory
    size: int
    in_use: bool = False

    @property
    def name(self) -> str:
        return self.shm.name

    @property
    def buf(self):
        return self.shm.buf


class ShmPool:
    def __init__(self, name_prefix: str = "sciqlop"):
        self._prefix = f"{name_prefix}_{os.getpid()}"
        self._segments: Dict[str, Segment] = {}
        self._counter = 0

    @property
    def segment_count(self) -> int:
        return len(self._segments)

    def acquire(self, nbytes: int) -> Segment:
        nbytes = max(int(nbytes), 1)
        for seg in self._segments.values():
            if not seg.in_use and seg.size >= nbytes:
                seg.in_use = True
                return seg
        self._counter += 1
        shm = shared_memory.SharedMemory(
            name=f"{self._prefix}_{self._counter}", create=True, size=nbytes,
            track=False,
        )
        seg = Segment(shm=shm, size=shm.size, in_use=True)
        self._segments[seg.name] = seg
        return seg

    def mark_reusable(self, name: str) -> None:
        seg = self._segments.get(name)
        if seg is not None:
            seg.in_use = False

    def unlink_all(self) -> None:
        for seg in self._segments.values():
            try:
                seg.shm.close()
                seg.shm.unlink()
            except FileNotFoundError:
                pass
        self._segments.clear()
