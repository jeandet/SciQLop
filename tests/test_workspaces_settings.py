from SciQLop.components.workspaces.backend.settings import SciQLopWorkspacesSettings


def test_reopen_last_workspace_defaults_true():
    s = SciQLopWorkspacesSettings()
    assert s.reopen_last_workspace is True
