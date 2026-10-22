import subprocess
import sys
from datetime import datetime, timezone

import pytest

from SciQLop.components.comparison.backend.dimensions import (
    COMPARISON_DIMENSIONS, apply_product, apply_settings, apply_time, base_range,
    contribute_core_dimensions, dimension, resolve_sides, validate_product, validate_settings, validate_time)
from SciQLop.components.comparison.backend.model import Comparison, Variant, base_specs
from SciQLop.components.plotting.panel_template import PanelTemplate, PlotModel, ProductModel, TimeRangeModel


def _iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def _comparison(time_range=(100.0, 200.0), variants=(), dimension="time", paths=(("a//b",),), knobs=None):
    plots = [PlotModel(products=[ProductModel(path=p, knobs=knobs or {}) for p in ps]) for ps in paths]
    rng = None if time_range is None else TimeRangeModel(start=_iso(time_range[0]), stop=_iso(time_range[1]))
    template = PanelTemplate(name="P", time_range=rng, plots=plots)
    return Comparison(base=template.to_tree(), dimension=dimension, variants=list(variants))


@pytest.fixture
def core_dimensions():
    """The production registrations are left in place: other test files rely on them."""
    contribute_core_dimensions()


def test_time_dimension_shifts_every_graph_by_anchor_difference():
    c = _comparison(variants=[Variant(label="e", params={"start": 1100.0, "stop": 1300.0})])
    side = apply_time(base_specs(c.template()), c.variants[0], c)
    assert {s.time_offset for s in side.specs} == {1000.0}
    assert (side.t0, side.duration) == (1100.0, 200.0)
    c2 = c.model_copy(update={"anchor": "end"})
    assert {s.time_offset for s in apply_time(base_specs(c2.template()), c2.variants[0], c2).specs} == {1100.0}


def test_time_dimension_adds_to_an_already_shifted_graph():
    c = _comparison(variants=[Variant(label="e", params={"start": 1100.0, "stop": 1300.0})])
    specs = [s.model_copy(update={"time_offset": 50.0}) for s in base_specs(c.template())]
    assert {s.time_offset for s in apply_time(specs, c.variants[0], c).specs} == {1050.0}


def test_time_dimension_refuses_base_without_range():
    c = _comparison(time_range=None, variants=[Variant(label="e", params={"start": 1.0, "stop": 2.0})])
    with pytest.raises(ValueError, match="no visible time range"):
        apply_time(base_specs(c.template()), c.variants[0], c)
    with pytest.raises(ValueError, match="no visible time range"):
        base_range(c)


def test_product_dimension_changes_only_target():
    c = _comparison(dimension="product", paths=(("a//b", "c//d"),),
                    variants=[Variant(label="v", params={"target": [0, 1], "path": "x//y", "is_colormap": True})])
    side = apply_product(base_specs(c.template()), c.variants[0], c)
    assert [(s.path, s.is_colormap) for s in side.specs] == [("a//b", False), ("x//y", True)]
    assert side.label == "v"


def test_settings_dimension_merges_knobs():
    c = _comparison(dimension="settings", knobs={"a": 1, "b": 2},
                    variants=[Variant(label="v", params={"target": [0, 0], "knobs": {"b": 3}})])
    side = apply_settings(base_specs(c.template()), c.variants[0], c)
    assert side.specs[0].knobs == {"a": 1, "b": 3}


def test_validate_rejects_missing_keys():
    with pytest.raises(ValueError, match="start"):
        validate_time({"stop": 1.0})
    with pytest.raises(ValueError, match="stop"):
        validate_time({"start": 2.0, "stop": 2.0})
    with pytest.raises(ValueError, match="path"):
        validate_product({"target": [0, 0]})
    with pytest.raises(ValueError, match="target"):
        validate_settings({"knobs": {}})


def test_contribute_core_dimensions_is_idempotent(core_dimensions):
    contribute_core_dimensions()
    assert [dimension(k).noun for k in ("time", "product", "settings")] == ["events", "products", "settings"]
    assert all(COMPARISON_DIMENSIONS.owner_of(k) == "sciqlop" for k in ("time", "product", "settings"))


def test_resolve_sides_puts_base_first(core_dimensions):
    c = _comparison(variants=[Variant(label="e", params={"start": 1100.0, "stop": 1300.0})])
    result = resolve_sides(c)
    assert [s.label for s in result] == ["P", "e"]
    assert (result[0].t0, result[0].duration) == (100.0, 100.0)


def _event(start, stop):
    return Variant(label=f"event {start:g}", params={"start": start, "stop": stop})


def test_the_event_the_base_window_is_centred_on_is_side_a(core_dimensions):
    c = _comparison(variants=[_event(120.0, 180.0), _event(1130.0, 1190.0)])
    a, b = resolve_sides(c)
    assert (a.label, a.t0) == ("event 120", 120.0)
    assert {s.time_offset for s in b.specs} == {1010.0}
    assert b.label == "event 1130"


def test_comparing_the_base_event_to_itself_shifts_nothing(core_dimensions):
    sides = resolve_sides(_comparison(variants=[_event(120.0, 180.0)]))
    assert [s.label for s in sides] == ["event 120"]


def test_a_shifted_copy_of_the_window_stays_a_variant(core_dimensions):
    a, b = resolve_sides(_comparison(variants=[_event(110.0, 210.0)]))
    assert (a.label, a.t0) == ("P", 100.0)
    assert {s.time_offset for s in b.specs} == {10.0}


def test_without_an_event_under_the_window_centre_side_a_is_the_window(core_dimensions):
    a, b, _ = resolve_sides(_comparison(variants=[_event(160.0, 190.0), _event(1160.0, 1190.0)]))
    assert (a.label, a.t0) == ("P", 100.0)
    assert {s.time_offset for s in b.specs} == {60.0}


def test_dimensions_module_does_not_import_qt_widgets():
    code = ("import SciQLop.components.comparison.backend.dimensions, sys; "
            "assert 'PySide6.QtWidgets' not in sys.modules")
    assert subprocess.run([sys.executable, "-I", "-c", code]).returncode == 0
