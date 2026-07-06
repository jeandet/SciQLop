"""Wire format + message tags for remote data sources.

Messages are plain tuples (tag-first) so they pickle trivially over a
multiprocessing pipe. Bulk arrays travel through shared memory; the pipe
carries only handles + this layout metadata.
"""
from __future__ import annotations

from typing import List, NamedTuple
import numpy as np

# main -> worker
INSTALL = "INSTALL"      # (INSTALL, channel_id, cloudpickle_blob, arity)
REQUEST = "REQUEST"      # (REQUEST, channel_id, req_id, start, stop, knobs)
FREE = "FREE"            # (FREE, channel_id, shm_name)
RELEASE = "RELEASE"      # (RELEASE, channel_id)
SHUTDOWN = "SHUTDOWN"    # (SHUTDOWN,)
# worker -> main
RESULT = "RESULT"        # (RESULT, channel_id, req_id, shm_name, layout, arity)
EMPTY = "EMPTY"          # (EMPTY, channel_id, req_id)
ERROR = "ERROR"          # (ERROR, channel_id, req_id, traceback_str)

_ALIGN = 8


class ArrayLayout(NamedTuple):
    shape: tuple
    dtype: str          # numpy dtype .str, e.g. '<f4'
    offset: int


def _aligned(n: int) -> int:
    return (n + _ALIGN - 1) // _ALIGN * _ALIGN


def total_nbytes(arrays: List[np.ndarray]) -> int:
    total = 0
    for a in arrays:
        total = _aligned(total) + a.nbytes
    return _aligned(total)


def pack_arrays(buf: memoryview, arrays: List[np.ndarray]) -> List[ArrayLayout]:
    layout: List[ArrayLayout] = []
    offset = 0
    for a in arrays:
        offset = _aligned(offset)
        a = np.ascontiguousarray(a)
        view = np.ndarray(a.shape, dtype=a.dtype, buffer=buf, offset=offset)
        view[...] = a
        layout.append(ArrayLayout(tuple(a.shape), a.dtype.str, offset))
        offset += a.nbytes
    return layout


def unpack_arrays(buf: memoryview, layout: List[ArrayLayout]) -> List[np.ndarray]:
    return [
        np.ndarray(tuple(l.shape), dtype=np.dtype(l.dtype), buffer=buf, offset=l.offset)
        for l in layout
    ]
