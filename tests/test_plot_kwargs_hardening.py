"""Backward-compatible promotion of plot **kwargs to explicit keyword params."""
import numpy as np
import pytest
from .fixtures import *

from SciQLop.user_api.plot._graphs import _UNSET, _with_explicit


def test_with_explicit_forwards_set_values():
    kwargs = {"existing": 1}
    out = _with_explicit(kwargs, labels=["a", "b"], name="g")
    assert out is kwargs                      # mutates and returns the same dict
    assert out == {"existing": 1, "labels": ["a", "b"], "name": "g"}


def test_with_explicit_skips_unset_values():
    out = _with_explicit({}, labels=_UNSET, name="g", colors=_UNSET)
    assert out == {"name": "g"}               # _UNSET params are not forwarded


def test_with_explicit_unset_is_falsy_safe():
    # A real value that is falsy (False / [] / 0) must still be forwarded.
    out = _with_explicit({}, y_log_scale=False, labels=[], graph_type=0)
    assert out == {"y_log_scale": False, "labels": [], "graph_type": 0}
