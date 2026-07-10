"""Rank a process's OS threads by CPU time consumed over a short window.

Reads `/proc/<pid>/task/*/stat` twice with a sleep in between -- needs no
ptrace/perf capability, unlike `py-spy`/`perf`, which require CAP_SYS_PTRACE/
CAP_PERFMON that a sandboxed dev environment (or a normal end user) may not
have. This is the tool to reach for first when a live SciQLop instance is
slow and a real profiler can't be attached: it tells you WHICH thread to
investigate before anything more invasive is needed.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadCpu:
    tid: int
    name: str
    cpu_seconds: float
    is_python: bool


def own_python_native_tids() -> frozenset[int]:
    """Native thread ids of every Python `threading.Thread` in this process.

    Only meaningful for `pid == os.getpid()` -- `native_id` has no relation
    to threads in a different process.
    """
    return frozenset(
        t.native_id for t in threading.enumerate() if t.native_id is not None
    )


def _list_tids(pid: int) -> list[int]:
    try:
        return [int(name) for name in os.listdir(f"/proc/{pid}/task")]
    except (FileNotFoundError, ProcessLookupError, NotADirectoryError):
        return []


def _read_name_and_ticks(pid: int, tid: int) -> tuple[str, int] | None:
    try:
        with open(f"/proc/{pid}/task/{tid}/stat") as f:
            raw = f.read()
    except (FileNotFoundError, ProcessLookupError):
        return None
    # comm (field 2) is parenthesized and may itself contain spaces/parens,
    # so split on the LAST ')' before treating the rest as space-separated.
    name_part, _, rest = raw.partition("(")
    name, _, fields_raw = rest.rpartition(")")
    fields = fields_raw.split()
    if len(fields) < 13:
        return None
    # After the ')', field 3 (state) is fields[0], so field 14 (utime) is
    # fields[11] and field 15 (stime) is fields[12].
    utime = int(fields[11])
    stime = int(fields[12])
    return name, utime + stime


def hot_threads(pid: int, window_s: float = 0.5) -> list[ThreadCpu]:
    """Threads of `pid` ranked by CPU time consumed during `window_s`.

    Only threads alive for the whole window are included -- a thread that
    appeared or vanished mid-window doesn't have a meaningful delta.
    """
    ticks_per_s = os.sysconf("SC_CLK_TCK")
    before = {
        tid: ticks
        for tid in _list_tids(pid)
        if (r := _read_name_and_ticks(pid, tid)) is not None
        for _name, ticks in [r]
    }
    time.sleep(window_s)
    native_tids = own_python_native_tids() if pid == os.getpid() else frozenset()

    out = []
    for tid in _list_tids(pid):
        if tid not in before:
            continue
        after = _read_name_and_ticks(pid, tid)
        if after is None:
            continue
        name, ticks_after = after
        delta_ticks = ticks_after - before[tid]
        out.append(ThreadCpu(
            tid=tid,
            name=name,
            cpu_seconds=max(delta_ticks, 0) / ticks_per_s,
            is_python=tid in native_tids,
        ))
    out.sort(key=lambda t: t.cpu_seconds, reverse=True)
    return out


def _format_table(threads: list[ThreadCpu]) -> str:
    lines = [f"{'TID':>8}  {'CPU s':>8}  {'py':>3}  NAME"]
    for t in threads:
        lines.append(f"{t.tid:>8}  {t.cpu_seconds:>8.2f}  {'Y' if t.is_python else 'n':>3}  {t.name}")
    return "\n".join(lines)


def _main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pid", type=int)
    parser.add_argument("--window", type=float, default=0.5,
                        help="sampling window in seconds (default: 0.5)")
    args = parser.parse_args()
    print(_format_table(hot_threads(args.pid, window_s=args.window)))


if __name__ == "__main__":
    _main()
