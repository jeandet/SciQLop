"""Turn a KernelManager.run_cell_capture() dict into nbformat output dicts."""
from __future__ import annotations

from typing import Any, Dict, List


def _split_error(error: str) -> tuple[str, str]:
    if error and ": " in error:
        ename, evalue = error.split(": ", 1)
        return ename, evalue
    return (error or "Error"), ""


def to_nbformat(captured: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    if captured.get("stdout"):
        outputs.append({"output_type": "stream", "name": "stdout",
                        "text": captured["stdout"]})
    if captured.get("stderr"):
        outputs.append({"output_type": "stream", "name": "stderr",
                        "text": captured["stderr"]})
    for d in captured.get("displays", []):
        outputs.append({"output_type": "display_data",
                        "data": d.get("data", {}), "metadata": d.get("metadata", {})})
    if captured.get("result") is not None:
        outputs.append({"output_type": "execute_result",
                        "execution_count": captured.get("execution_count"),
                        "data": {"text/plain": captured["result"]}, "metadata": {}})
    if not captured.get("success", True):
        ename, evalue = _split_error(captured.get("error") or "")
        outputs.append({"output_type": "error", "ename": ename, "evalue": evalue,
                        "traceback": list(captured.get("traceback") or [])})
    return outputs
