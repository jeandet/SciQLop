def test_new_kernel_tools_present(qtbot):
    from SciQLop.components.agents.tools._builder import build_sciqlop_tools

    class _MW:  # minimal stand-in; building tools must not require a live window
        def __getattr__(self, _):
            return None

    tools = build_sciqlop_tools(_MW())
    names = {t["name"] for t in tools}
    assert {"sciqlop_run_notebook_cell", "sciqlop_interrupt_kernel",
            "sciqlop_kernel_vars", "sciqlop_inspect"} <= names
    gated = {t["name"]: t.get("gated", False) for t in tools}
    assert gated["sciqlop_interrupt_kernel"] is True
    assert gated["sciqlop_kernel_vars"] is False
    assert gated["sciqlop_inspect"] is False
