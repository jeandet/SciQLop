import time
import pytest
from SciQLop.components.jupyter.kernel.manager import KernelManager


@pytest.mark.timeout(30)
def test_interrupt_stops_a_long_cell(qtbot):
    km = KernelManager()
    km.start(port=0)
    try:
        fut = km.submit_cell("import time\nfor _ in range(100):\n    time.sleep(0.1)")
        qtbot.wait(300)              # let the cell get going
        km.interrupt()               # must raise KeyboardInterrupt in the cell
        result = fut.result(timeout=10)
        assert result["success"] is False
        assert "KeyboardInterrupt" in (result["error"] or "")
    finally:
        km.shutdown()
