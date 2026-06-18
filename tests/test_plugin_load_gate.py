"""Loader backstop: don't load a folder plugin incompatible with the host."""
import json

import SciQLop
from SciQLop.components.plugins.backend.loader.loader import plugin_host_compatible


def _make_plugin(folder, name, python_dependencies):
    pdir = folder / name
    pdir.mkdir(parents=True)
    (pdir / "plugin.json").write_text(json.dumps({
        "name": name,
        "version": "1.0.0",
        "description": "x",
        "authors": [{"name": "a", "email": "a@b.c", "organization": "o"}],
        "license": "MIT",
        "python_dependencies": python_dependencies,
    }))
    return pdir


def test_incompatible_plugin_is_gated_out(tmp_path, monkeypatch):
    monkeypatch.setattr(SciQLop, "__version__", "0.13.0.dev0")
    _make_plugin(tmp_path, "future_plugin", ["SciQLop>=0.20", "numpy"])
    assert plugin_host_compatible(str(tmp_path), "future_plugin") is False


def test_dev_build_loads_plugin_targeting_its_release(tmp_path, monkeypatch):
    monkeypatch.setattr(SciQLop, "__version__", "0.13.0.dev0")
    _make_plugin(tmp_path, "ok_plugin", ["SciQLop>=0.13.0,<0.14.0", "speasy>=1.7"])
    assert plugin_host_compatible(str(tmp_path), "ok_plugin") is True


def test_plugin_without_sciqlop_requirement_loads(tmp_path, monkeypatch):
    monkeypatch.setattr(SciQLop, "__version__", "0.13.0.dev0")
    _make_plugin(tmp_path, "no_req", ["numpy", "matplotlib>=3.8"])
    assert plugin_host_compatible(str(tmp_path), "no_req") is True


def test_missing_plugin_json_is_not_gated(tmp_path):
    (tmp_path / "bare_module").mkdir()
    assert plugin_host_compatible(str(tmp_path), "bare_module") is True


def test_malformed_plugin_json_is_not_gated_here(tmp_path):
    pdir = tmp_path / "broken"
    pdir.mkdir()
    (pdir / "plugin.json").write_text("{ not json")
    assert plugin_host_compatible(str(tmp_path), "broken") is True
