import nbformat


def test_disk_sink_writes_outputs_and_count(tmp_path, qtbot):
    # qtbot provides a QApplication so importing the agents.tools package
    # (which transitively loads SciQLopPlots bindings) does not abort.
    from SciQLop.components.agents.tools._notebook_sink import DiskNotebookSink

    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("1+1")]
    p = tmp_path / "n.ipynb"
    nbformat.write(nb, str(p))

    outputs = [{"output_type": "execute_result", "execution_count": 7,
                "data": {"text/plain": "2"}, "metadata": {}}]
    # explicit resolve avoids depending on _resolve_notebook's workspace path logic
    DiskNotebookSink(resolve=lambda rel: p).write_outputs(str(p), 0, outputs, 7)

    reloaded = nbformat.read(str(p), as_version=4)
    cell = reloaded.cells[0]
    assert cell["execution_count"] == 7
    assert cell["outputs"][0]["data"]["text/plain"] == "2"
