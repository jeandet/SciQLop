"""Install Python packages into the active workspace and persist them.

Unlike a raw ``pip install``, ``install_packages`` records the packages in the
workspace manifest (``workspace.sciqlop``), so they are reinstalled on the next
launch and survive venv recreation.
"""
from __future__ import annotations

from SciQLop.components.workspaces import workspaces_manager_instance


def install_packages(*specs: str) -> dict:
    """Install one or more packages into the active workspace and record them.

    Accepts PEP 508 specifiers (e.g. ``"astropy"``, ``"scipy>=1.11"``). Returns
    ``{"ok": bool, "installed": list, "already_present": list, "error": str}``.
    """
    wm = workspaces_manager_instance()
    if wm is None or not getattr(wm, "has_workspace", False):
        return {"ok": False, "installed": [],
                "already_present": [], "error": "no active workspace"}
    return wm.workspace.add_packages(list(specs))
