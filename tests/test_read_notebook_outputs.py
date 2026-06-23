import nbformat


def test_read_notebook_includes_outputs(tmp_path, qtbot, monkeypatch):
    from SciQLop.components.agents.tools import notebooks  # inside body: qtbot gives QApplication

    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell("print('x')")
    cell["outputs"] = [
        nbformat.from_dict({"output_type": "stream", "name": "stdout", "text": "x\n"}),
        nbformat.from_dict({"output_type": "error", "ename": "ValueError", "evalue": "boom",
                            "traceback": ["tb1", "tb2"]}),
        nbformat.from_dict({"output_type": "display_data", "data": {"image/png": "B64"},
                            "metadata": {}}),
    ]
    nb.cells = [cell]
    p = tmp_path / "n.ipynb"
    nbformat.write(nb, str(p))
    monkeypatch.setattr(notebooks, "_resolve_notebook", lambda rel: p)

    text = notebooks.read_notebook(str(p))
    assert "x" in text                            # stream text
    assert "ValueError: boom" in text             # error
    assert "[image: image/png]" in text           # image marker, not the base64
    assert "B64" not in text
