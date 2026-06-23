"""Where run-cell outputs are written. Disk now; an RTC-backed sink can replace
DiskNotebookSink later without touching the run_cell tool."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Protocol


class NotebookSink(Protocol):
    def write_outputs(self, rel_path: str, index: int,
                      outputs: List[Dict[str, Any]], execution_count: int) -> None:
        ...


class DiskNotebookSink:
    """Write cell outputs + execution_count into the .ipynb on disk. JupyterLab's
    file-watcher reloads it."""

    def __init__(self, resolve: Any = None) -> None:
        # resolve(rel_path) -> absolute Path; defaults to notebooks._resolve_notebook
        self._resolve = resolve

    def _path(self, rel_path: str) -> Path:
        if self._resolve is not None:
            return Path(self._resolve(rel_path))
        from . import notebooks
        return notebooks._resolve_notebook(rel_path)

    def write_outputs(self, rel_path: str, index: int,
                      outputs: List[Dict[str, Any]], execution_count: int) -> None:
        import nbformat
        path = self._path(rel_path)
        nb = nbformat.read(str(path), as_version=4)
        cell = nb.cells[index]
        cell["outputs"] = [nbformat.from_dict(o) for o in outputs]
        cell["execution_count"] = execution_count
        nbformat.write(nb, str(path))
