import nbformat
import pytest
from SciQLop.components.jupyter.kernel.manager import KernelManager


@pytest.mark.timeout(40)
def test_run_cell_writes_outputs_and_summarizes(tmp_path, qtbot, monkeypatch):
    from SciQLop.components.agents.tools import notebooks
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("print('hi')\n6 * 7")]
    p = tmp_path / "nb.ipynb"
    nbformat.write(nb, str(p))
    monkeypatch.setattr(notebooks, "_resolve_notebook", lambda rel: p)

    km = KernelManager()
    km.start(port=0)
    try:
        summary = notebooks.run_cell(km, str(p), 0).result(timeout=20)
        assert "42" in summary and "[1]" in summary    # result + execution_count
        reloaded = nbformat.read(str(p), as_version=4)
        outs = reloaded.cells[0]["outputs"]
        assert any(o["output_type"] == "stream" and "hi" in o["text"] for o in outs)
        assert reloaded.cells[0]["execution_count"] == 1
    finally:
        km.shutdown()
