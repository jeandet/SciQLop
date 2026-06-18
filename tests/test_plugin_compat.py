"""Dev-build-aware SciQLop ↔ plugin compatibility (components/plugins/compat.py)."""
from SciQLop.components.plugins.compat import (
    host_satisfies, sciqlop_specifier, plugin_is_compatible,
)


class TestHostSatisfies:
    def test_dev_build_satisfies_its_target_release_floor(self):
        # The reported bug: 0.13.0.dev0 must satisfy a plugin needing >=0.13.0.
        assert host_satisfies(">=0.13.0,<0.14.0", "0.13.0.dev0") is True

    def test_dev_build_excluded_from_previous_line(self):
        assert host_satisfies(">=0.12.0,<0.13.0", "0.13.0.dev0") is False

    def test_dev_build_excluded_from_future_floor(self):
        assert host_satisfies(">=0.20", "0.13.0.dev0") is False

    def test_released_host_matches_normally(self):
        assert host_satisfies(">=0.13.0,<0.14.0", "0.13.5") is True
        assert host_satisfies(">=0.14.0", "0.13.5") is False

    def test_empty_spec_is_compatible(self):
        assert host_satisfies("", "0.13.0.dev0") is True
        assert host_satisfies(None, "0.13.0.dev0") is True

    def test_invalid_spec_is_treated_as_compatible(self):
        assert host_satisfies("not a spec", "0.13.0.dev0") is True


class TestSciqlopSpecifier:
    def test_single_specifier_extracted(self):
        from packaging.specifiers import SpecifierSet
        spec = sciqlop_specifier(["SciQLop>=0.13.0,<0.14.0", "numpy>=1.24"])
        assert SpecifierSet(spec) == SpecifierSet(">=0.13.0,<0.14.0")

    def test_multiple_sciqlop_entries_intersected(self):
        spec = sciqlop_specifier(["SciQLop>=0.13.0", "sciqlop<0.14.0", "matplotlib"])
        assert host_satisfies(spec, "0.13.0.dev0") is True
        assert host_satisfies(spec, "0.14.1") is False

    def test_no_sciqlop_requirement_is_empty(self):
        assert sciqlop_specifier(["numpy", "matplotlib>=3.8"]) == ""

    def test_url_and_bare_names_ignored(self):
        deps = ["https://example.com/x-0.1-py3-none-any.whl", "SciQLop>=0.13.0"]
        assert sciqlop_specifier(deps) == ">=0.13.0"


class TestPluginIsCompatible:
    def test_compatible_dev_build(self):
        assert plugin_is_compatible(["SciQLop>=0.13.0,<0.14.0", "speasy>=1.7"], "0.13.0.dev0") is True

    def test_incompatible_future_requirement(self):
        assert plugin_is_compatible(["SciQLop>=0.20"], "0.13.0.dev0") is False

    def test_no_requirement_is_compatible(self):
        assert plugin_is_compatible(["numpy", "speasy"], "0.13.0.dev0") is True
