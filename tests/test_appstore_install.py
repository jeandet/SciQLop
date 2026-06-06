"""AppStore plugin install behind a corporate HTTP proxy.

Two regressions guarded here:

1. ``--native-tls`` — corporate proxies MITM HTTPS with a private root CA that
   lives in the OS certificate store but not in uv's bundled bundle. Without
   ``--native-tls`` uv rejects the intercepted certificate and the install
   fails. The flag makes uv trust the platform store (and the corporate CA).

2. Error visibility — a failed ``uv pip install`` raises ``CalledProcessError``,
   whose ``str()`` is only "Command '…' returned non-zero exit status 1." The
   real cause (proxy/TLS/auth) is in ``.stderr``; the appstore must surface it
   instead of a bare "Failed", otherwise the failure is undiagnosable.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from SciQLop.components.appstore.backend import (
    _uv_install_cmd,
    _uv_uninstall_cmd,
    _error_detail,
    _write_requirements_file,
)
from SciQLop.components.workspaces.backend.uv import find_uv


@pytest.mark.skipif(find_uv() is None, reason="uv binary not available")
class TestNativeTls:
    def test_install_cmd_requests_native_tls(self):
        cmd = _uv_install_cmd("some-plugin==1.2.3")
        assert "--native-tls" in cmd
        assert cmd[-1] == "some-plugin==1.2.3"

    def test_uninstall_cmd_requests_native_tls(self):
        cmd = _uv_uninstall_cmd("some-plugin")
        assert "--native-tls" in cmd
        assert cmd[-1] == "some-plugin"


@pytest.mark.skipif(find_uv() is None, reason="uv binary not available")
class TestHostIsolation:
    """The appstore install must not pull host-provided packages (SciQLop and
    the pinned base stack) from PyPI. A plugin wheel declares
    ``Requires-Dist: SciQLop>=X``; without an override uv resolves it against
    PyPI and drags a mismatched SciQLop + pyside6/speasy/shiboken6 into the
    workspace venv — the failure a user hit installing onto a 0.12.1.dev0 build.
    """

    def test_install_cmd_passes_override_and_constraint(self):
        cmd = _uv_install_cmd(
            "some-plugin==1.2.3",
            override_file="/tmp/overrides.txt",
            constraint_file="/tmp/constraints.txt",
        )
        assert cmd[cmd.index("--override") + 1] == "/tmp/overrides.txt"
        assert cmd[cmd.index("--constraint") + 1] == "/tmp/constraints.txt"
        # The package spec must stay last so uv treats it as the install target.
        assert cmd[-1] == "some-plugin==1.2.3"

    def test_install_cmd_omits_flags_when_no_files(self):
        cmd = _uv_install_cmd("some-plugin==1.2.3")
        assert "--override" not in cmd
        assert "--constraint" not in cmd


class TestWriteRequirementsFile:
    def test_returns_none_for_empty_lines(self):
        with tempfile.TemporaryDirectory() as d:
            assert _write_requirements_file(d, "x.txt", []) is None

    def test_writes_file_and_returns_path(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write_requirements_file(d, "overrides.txt", ["sciqlop ; python_version < '0'"])
            assert path is not None
            assert Path(path).read_text() == "sciqlop ; python_version < '0'\n"


class TestErrorDetail:
    def test_prefers_subprocess_stderr(self):
        exc = subprocess.CalledProcessError(
            1, ["uv", "pip", "install"],
            stderr="error: TLS connect: certificate verify failed (proxy CA)",
        )
        detail = _error_detail(exc)
        assert "certificate verify failed" in detail
        assert "returned non-zero exit status" not in detail

    def test_falls_back_to_str_when_no_stderr(self):
        assert "boom" in _error_detail(RuntimeError("boom"))

    def test_ignores_empty_stderr(self):
        exc = subprocess.CalledProcessError(1, ["uv"], stderr="")
        # empty stderr must not produce an empty, useless message
        assert _error_detail(exc).strip() != ""
