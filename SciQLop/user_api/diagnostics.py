"""Diagnostic tooling for SciQLop. Re-exports `SciQLop.components.profiling`.

Quick start (from the embedded Jupyter console) -- useful when SciQLop feels
slow *right now* and some OTHER thread might be the stuck one:

>>> from SciQLop.user_api import diagnostics
>>> path = diagnostics.dump_now("slow-pan")
>>> diagnostics.hot_threads(os.getpid())   # rank OS threads by CPU, no root needed

Or from outside the app entirely, no elevated privilege needed:

    kill -USR1 <pid>   # appends an all-threads dump to the diagnostics dir
"""
from SciQLop.components.profiling.hang_dump import (  # noqa: F401
    dump_now, install_signal_dump, uninstall_signal_dump, default_directory,
)
from SciQLop.components.profiling.thread_cpu_top import (  # noqa: F401
    hot_threads, own_python_native_tids,
)

__all__ = [
    "dump_now", "install_signal_dump", "uninstall_signal_dump", "default_directory",
    "hot_threads", "own_python_native_tids",
]
