"""Return the current matplotlib figure from the embedded kernel as PNG.

The embedded kernel shares this process, so pyplot's global figure registry is
the same module singleton — no need to round-trip through the kernel.
"""
from __future__ import annotations

from typing import Optional


def current_figure_png() -> Optional[bytes]:
    import io
    import matplotlib.pyplot as plt
    if not plt.get_fignums():
        return None
    buf = io.BytesIO()
    plt.gcf().savefig(buf, format="png", bbox_inches="tight")
    return buf.getvalue()
