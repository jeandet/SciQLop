"""Agent tools must never block the GUI/event-loop thread.

Root cause (confirmed via py-spy on a frozen live session): the in-process MCP
tool handlers ran inline on the qasync loop == Qt GUI thread. `sciqlop_exec_python`
in particular ran `shell.run_cell` directly there, so a blocking cell (e.g. a slow
speasy fetch) froze the whole UI — sometimes for hours. The fix runs exec_python on
the kernel thread and thread-tagged tools off the loop.

All checks run in a FRESH subprocess (`_kernel_subproc_checks.py`): creating a real
IPython kernel in this shared pytest-qt process leaves residue that later SIGSEGVs the
GUI suite's `load_all`. A separate interpreter has its own memory and cannot pollute
this process — so the suite stays stable while we still exercise the real kernel path.
"""
import os
import subprocess
import sys


def test_agent_exec_and_tool_offloading():
    script = os.path.join(os.path.dirname(__file__), "_kernel_subproc_checks.py")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    proc = subprocess.run(
        [sys.executable, script],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert proc.returncode == 0, f"\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert "ALL OK" in proc.stdout
