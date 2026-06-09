from datetime import timedelta
from typing import Annotated

from speasy.products import SpeasyVariable

from SciQLop.components.plotting.backend.dependencies import (
    Depends, DependsSpec, depends_marker, extract_dependencies_from_callback,
)


def test_extracts_path_dependency():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("speasy//amda//imf", pad=60.0)]):
        return None
    specs = extract_dependencies_from_callback(f)
    assert specs == [DependsSpec(name="b", target="speasy//amda//imf", pad=60.0)]


def test_pad_timedelta_normalized_to_seconds():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("p", pad=timedelta(minutes=1))]):
        return None
    assert extract_dependencies_from_callback(f)[0].pad == 60.0


def test_no_pad_defaults_to_zero():
    def f(start: float, stop: float,
          b: Annotated[SpeasyVariable, Depends("p")]):
        return None
    assert extract_dependencies_from_callback(f)[0].pad == 0.0


def test_ignores_params_without_marker():
    def f(start: float, stop: float, fft: int = 256):
        return None
    assert extract_dependencies_from_callback(f) == []


def test_depends_marker_detects_annotation():
    annot = Annotated[SpeasyVariable, Depends("p")]
    assert depends_marker(annot) is not None
    assert depends_marker(SpeasyVariable) is None


def test_extracts_multiple_dependencies():
    def f(start: float, stop: float,
          a: Annotated[SpeasyVariable, Depends("x")],
          b: Annotated[SpeasyVariable, Depends("y", pad=5.0)]):
        return None
    specs = extract_dependencies_from_callback(f)
    assert [(s.name, s.target, s.pad) for s in specs] == [("a", "x", 0.0), ("b", "y", 5.0)]
