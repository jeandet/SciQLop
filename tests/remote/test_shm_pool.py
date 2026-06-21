import pytest
from SciQLop.components.plotting.backend.remote.shm_pool import ShmPool


def test_acquire_then_reuse_same_segment_after_free():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(100)
        name1 = s1.name
        pool.mark_reusable(name1)
        s2 = pool.acquire(50)          # fits in the freed 100-byte segment
        assert s2.name == name1        # reused, not a new segment
        assert pool.segment_count == 1
    finally:
        pool.unlink_all()


def test_acquire_while_out_allocates_new_segment():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(100)         # still out (not freed)
        s2 = pool.acquire(100)
        assert s1.name != s2.name
        assert pool.segment_count == 2
    finally:
        pool.unlink_all()


def test_acquire_grows_when_free_segment_too_small():
    pool = ShmPool(name_prefix="sciqlop_test")
    try:
        s1 = pool.acquire(10)
        pool.mark_reusable(s1.name)
        s2 = pool.acquire(1000)        # too big for the 10-byte free one
        assert s2.size >= 1000
    finally:
        pool.unlink_all()


def test_unlink_all_removes_segments():
    from multiprocessing import shared_memory
    pool = ShmPool(name_prefix="sciqlop_test")
    s = pool.acquire(64)
    name = s.name
    pool.unlink_all()
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory(name=name)
