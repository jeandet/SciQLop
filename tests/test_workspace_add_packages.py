"""Workspace.add_packages: install via uv + record in manifest, structured result."""
from types import SimpleNamespace

from SciQLop.components.workspaces.backend.workspace import Workspace
from SciQLop.components.workspaces.backend.workspace_manifest import WorkspaceManifest


def _make_ws(tmp_path, requires=None):
    # Bypass the QObject __init__ so the test needs no QApplication.
    m = WorkspaceManifest(name="T", requires=list(requires or []))
    m.save(tmp_path / "workspace.sciqlop")          # sets m.directory = tmp_path
    ws = Workspace.__new__(Workspace)
    ws._manifest = m
    ws._manifest_path = tmp_path / "workspace.sciqlop"
    return ws


def test_installs_new_package_and_records(tmp_path):
    ws = _make_ws(tmp_path)
    calls = []
    ws._uv_install = lambda pkgs: calls.append(pkgs) or SimpleNamespace(
        returncode=0, stdout="ok", stderr="")
    result = ws.add_packages(["astropy"])
    assert result == {"ok": True, "installed": ["astropy"],
                      "already_present": [], "error": ""}
    assert calls == [["astropy"]]
    assert "astropy" in ws._manifest.requires
    # persisted
    assert "astropy" in WorkspaceManifest.load(tmp_path / "workspace.sciqlop").requires


def test_already_present_skips_uv(tmp_path):
    ws = _make_ws(tmp_path, requires=["astropy"])
    ws._uv_install = lambda pkgs: (_ for _ in ()).throw(AssertionError("uv called"))
    result = ws.add_packages(["astropy"])
    assert result == {"ok": True, "installed": [],
                      "already_present": ["astropy"], "error": ""}


def test_mix_installs_only_new(tmp_path):
    ws = _make_ws(tmp_path, requires=["astropy"])
    ws._uv_install = lambda pkgs: SimpleNamespace(returncode=0, stdout="", stderr="")
    result = ws.add_packages(["astropy", "scipy"])
    assert result["installed"] == ["scipy"]
    assert result["already_present"] == ["astropy"]
    assert "scipy" in ws._manifest.requires


def test_failed_install_leaves_manifest_untouched(tmp_path):
    ws = _make_ws(tmp_path)
    ws._uv_install = lambda pkgs: SimpleNamespace(
        returncode=1, stdout="", stderr="No match for nonexistent-xyz")
    result = ws.add_packages(["nonexistent-xyz"])
    assert result["ok"] is False
    assert result["installed"] == []
    assert "No match" in result["error"]
    assert ws._manifest.requires == []
    assert WorkspaceManifest.load(tmp_path / "workspace.sciqlop").requires == []


def test_repin_replaces_existing_entry(tmp_path):
    # Recorded "scipy"; installing "scipy>=1.11" re-pins it (last-wins), so the
    # manifest holds only the new spec, not both.
    ws = _make_ws(tmp_path, requires=["scipy"])
    ws._uv_install = lambda pkgs: SimpleNamespace(returncode=0, stdout="", stderr="")
    result = ws.add_packages(["scipy>=1.11"])
    assert result["installed"] == ["scipy>=1.11"]
    assert ws._manifest.requires == ["scipy>=1.11"]
    assert WorkspaceManifest.load(tmp_path / "workspace.sciqlop").requires == ["scipy>=1.11"]


def test_no_duplicate_same_package_within_one_call(tmp_path):
    ws = _make_ws(tmp_path)
    ws._uv_install = lambda pkgs: SimpleNamespace(returncode=0, stdout="", stderr="")
    ws.add_packages(["scipy", "scipy>=1.11"])
    assert ws._manifest.requires == ["scipy>=1.11"]


def test_failed_repin_leaves_existing_entry_untouched(tmp_path):
    ws = _make_ws(tmp_path, requires=["scipy"])
    ws._uv_install = lambda pkgs: SimpleNamespace(returncode=1, stdout="", stderr="boom")
    result = ws.add_packages(["scipy>=1.11"])
    assert result["ok"] is False
    assert ws._manifest.requires == ["scipy"]
