from unittest.mock import patch
import pytest


@pytest.fixture
def tmp_config_dir(tmp_path):
    with patch("SciQLop.components.settings.backend.entry.SCIQLOP_CONFIG_DIR", str(tmp_path)):
        yield tmp_path


def test_defaults(tmp_config_dir):
    from SciQLop.components.smart_search.settings import SmartSearchSettings
    s = SmartSearchSettings()
    assert s.enabled is False
    assert s.model == "minishlab/potion-base-8M"


def test_category_and_subcategory(tmp_config_dir):
    from SciQLop.components.smart_search.settings import SmartSearchSettings
    from SciQLop.components.settings import SettingsCategory
    assert SmartSearchSettings.category == SettingsCategory.APPLICATION
    assert SmartSearchSettings.subcategory == "Smart Search"


def test_persists_across_instances(tmp_config_dir):
    from SciQLop.components.smart_search.settings import SmartSearchSettings
    with SmartSearchSettings() as s:
        s.enabled = True
        s.model = "minishlab/potion-base-32M"
    s2 = SmartSearchSettings()
    assert s2.enabled is True
    assert s2.model == "minishlab/potion-base-32M"
