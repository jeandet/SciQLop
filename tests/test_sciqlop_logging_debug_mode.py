from SciQLop.components.sciqlop_logging import is_debug_mode


def test_is_debug_mode_false_when_unset(monkeypatch):
    monkeypatch.delenv("SCIQLOP_DEBUG", raising=False)
    assert is_debug_mode() is False


def test_is_debug_mode_true_when_set(monkeypatch):
    monkeypatch.setenv("SCIQLOP_DEBUG", "1")
    assert is_debug_mode() is True


def test_is_debug_mode_true_when_set_empty(monkeypatch):
    # presence, not truthiness of the value, is what matters -- matches the
    # existing `'SCIQLOP_DEBUG' in os.environ` check in logger.py's module
    # level log-level setup.
    monkeypatch.setenv("SCIQLOP_DEBUG", "")
    assert is_debug_mode() is True
