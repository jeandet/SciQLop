"""Always-on statistical sampling profiler.

Fills a gap the zone-based tracer (`SciQLop.core.tracing`) can't: code
nobody hand-instrumented (third-party libraries, an un-wrapped hot loop)
stays invisible to it even with a trace running. This periodically samples
`sys._current_frames()` into a bounded ring buffer -- cheap enough to leave
running, flushed on demand or when the watchdog (watchdog.py) trips, showing
what every thread was doing in the seconds leading up to a stall even though
no zone existed at that callsite.

Ships default-off (see watchdog.py / sciqlop_application.py wiring) pending
a real overhead measurement -- not assumed safe to enable by default.
"""
from __future__ import annotations

import datetime
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, List, Optional

from SciQLop.components.storage import user_data_dir


@dataclass(frozen=True)
class Sample:
    timestamp: float
    tid: int
    thread_name: str
    frames: List[str]  # top `frame_depth` "file:line in func", innermost first


def _summarize(frame, depth: int) -> List[str]:
    out: List[str] = []
    f = frame
    while f is not None and len(out) < depth:
        code = f.f_code
        out.append(f"{code.co_filename}:{f.f_lineno} in {code.co_name}")
        f = f.f_back
    return out


class Sampler:
    def __init__(self, interval_s: float = 0.2, max_samples: int = 3000, frame_depth: int = 3):
        self._interval_s = interval_s
        self._frame_depth = frame_depth
        self._buffer: Deque[Sample] = deque(maxlen=max_samples)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="sciqlop-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s * 4 + 1)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.is_set():
            self._sample_once()
            self._stop.wait(self._interval_s)

    def _sample_once(self) -> None:
        now = time.time()
        names = {t.ident: t.name for t in threading.enumerate()}
        entries = [
            Sample(now, tid, names.get(tid, f"tid-{tid}"), _summarize(frame, self._frame_depth))
            for tid, frame in sys._current_frames().items()
        ]
        with self._lock:
            self._buffer.extend(entries)

    def snapshot(self) -> List[Sample]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


def default_directory() -> Path:
    return user_data_dir("diagnostics")


_sampler: Optional[Sampler] = None


def get_sampler() -> Sampler:
    """The process-wide sampler singleton, built from current settings the
    first time it's needed (so tests never construct one implicitly just by
    importing this module)."""
    global _sampler
    if _sampler is None:
        from .settings import ProfilingSettings
        settings = ProfilingSettings()
        rounds = settings.sample_buffer_seconds * 1000 // settings.sample_interval_ms
        # ~50 threads/round is a generous margin over the ~30-40 threads seen
        # in a real SciQLop instance; the deque just caps, so over-sizing is
        # cheap and under-sizing is the only real failure mode.
        _sampler = Sampler(
            interval_s=settings.sample_interval_ms / 1000,
            max_samples=rounds * 50,
            frame_depth=3,
        )
    return _sampler


def maybe_start_from_settings() -> None:
    """Start the singleton sampler iff ProfilingSettings.sampler_enabled."""
    from .settings import ProfilingSettings
    if ProfilingSettings().sampler_enabled:
        get_sampler().start()


def flush_to_file(sampler: Sampler, directory: Optional[Path], reason: str) -> Path:
    """Write the current ring-buffer contents to a fresh timestamped file."""
    directory = directory or default_directory()
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"sampler-{stamp}-{reason}.txt"
    with open(path, "w") as f:
        f.write(f"# SciQLop sampler dump\n# reason: {reason}\n"
                f"# time: {now.isoformat()}\n\n")
        for s in sampler.snapshot():
            f.write(f"[{s.timestamp:.3f}] {s.thread_name} (tid={s.tid})\n")
            for frame_line in s.frames:
                f.write(f"    {frame_line}\n")
    return path
