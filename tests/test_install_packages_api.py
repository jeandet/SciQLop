"""user_api.install_packages: resolve active workspace and delegate to add_packages."""
from unittest.mock import MagicMock

import SciQLop.user_api.packages as pkgs


def test_no_active_workspace(monkeypatch):
    monkeypatch.setattr(pkgs, "workspaces_manager_instance", lambda: None)
    result = pkgs.install_packages("astropy")
    assert result == {"ok": False, "installed": [],
                      "already_present": [], "error": "no active workspace"}


def test_delegates_to_add_packages(monkeypatch):
    ws = MagicMock()
    ws.add_packages.return_value = {"ok": True, "installed": ["scipy"],
                                    "already_present": [], "error": ""}
    wm = MagicMock(has_workspace=True, workspace=ws)
    monkeypatch.setattr(pkgs, "workspaces_manager_instance", lambda: wm)
    result = pkgs.install_packages("scipy", "astropy>=5")
    ws.add_packages.assert_called_once_with(["scipy", "astropy>=5"])
    assert result["installed"] == ["scipy"]
