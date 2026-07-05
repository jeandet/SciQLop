import numpy as np
from .protocol import Plot, Plottable
from typing import Optional, Union, List
from ..virtual_products import VirtualProduct
from SciQLopPlots import SciQLopHistogram2D as _SciQLopHistogram2D
from SciQLopPlots import SciQLopColorMapBase as _SciQLopColorMapBase
from ._thread_safety import on_main_thread
from SciQLop.core import tracing as _tracing

from SciQLop.components.sciqlop_logging import getLogger as _getLogger

__all__ = ['Graph', 'ColorMap', 'Histogram2D']

log = _getLogger(__name__)

AnyProductType = Union[str, VirtualProduct, List[str]]


def is_array_of_double(a):
    return isinstance(a, np.ndarray) and a.dtype == np.float64


def _to_float64(a):
    if a is None:
        return None
    arr = a if isinstance(a, np.ndarray) else np.asarray(a)
    if arr.ndim == 0:
        raise ValueError("scalar (0-d) data is not plottable; pass a 1-D array")
    if np.issubdtype(arr.dtype, np.complexfloating):
        raise ValueError(
            "complex data is not plottable; take .real, .imag or np.abs() "
            "explicitly")
    if arr.dtype == np.float64:
        return np.ascontiguousarray(arr)
    if np.issubdtype(arr.dtype, np.datetime64):
        from speasy.core import datetime64_to_epoch
        return np.ascontiguousarray(datetime64_to_epoch(arr))
    return np.ascontiguousarray(arr.astype(np.float64))


def ensure_arrays_of_double(*args):
    return tuple(_to_float64(a) for a in args)


_UNSET = object()


def _with_explicit(kwargs: dict, **named) -> dict:
    """Fold caller-set keyword params into the forwarded ``kwargs`` dict.

    Values left as the ``_UNSET`` sentinel are not inserted, preserving the
    exact present/absent semantics the ``**kwargs`` passthrough had before
    these options were promoted to explicit keyword parameters. Falsy real
    values (``False``, ``[]``, ``0``) are forwarded; only ``_UNSET`` is skipped.
    """
    for key, value in named.items():
        if value is not _UNSET:
            kwargs[key] = value
    return kwargs


def _len_safe(a):
    try:
        return int(len(a))
    except TypeError:
        return 0


_VALID_Y_AXES = ("y", "y2")


def _wire_destroyed(wrapper, impl):
    """Clear the wrapper's impl when the C++ object dies, so stale handles
    raise a friendly ValueError instead of a cryptic Shiboken RuntimeError."""
    try:
        impl.destroyed.connect(wrapper._on_destroyed)
    except (AttributeError, RuntimeError):
        pass


class Graph(Plottable):
    def __init__(self, impl, plot=None):
        self._impl = impl
        self._plot = plot
        _wire_destroyed(self, impl)

    def _on_destroyed(self):
        self._impl = None

    def _get_impl_or_raise(self):
        if self._impl is None:
            raise ValueError("The graph does not exist anymore.")
        return self._impl

    @property
    @on_main_thread
    def y_axis(self) -> Optional[str]:
        """Which y-axis this graph is attached to: ``"y"`` or ``"y2"``.

        Returns ``None`` if the parent plot reference is not available
        (e.g. graphs created through low-level paths that don't carry it).
        """
        if self._plot is None:
            return None
        plot_impl = self._plot._get_impl_or_raise()
        current = self._get_impl_or_raise().y_axis()
        if current is plot_impl.y2_axis():
            return "y2"
        return "y"

    @y_axis.setter
    @on_main_thread
    def y_axis(self, name: str) -> None:
        if name not in _VALID_Y_AXES:
            raise ValueError(
                f"axis {name!r} not valid for a graph (expected one of: y, y2)"
            )
        if self._plot is None:
            raise RuntimeError(
                "cannot retarget this graph: its parent plot reference is unset"
            )
        self._get_impl_or_raise().set_y_axis(self._plot._resolve_axis(name))

    @on_main_thread
    def set_data(self, x, y):
        with _tracing.zone("Graph.set_data", cat="plot", n_points=_len_safe(x)):
            with _tracing.zone("ensure_arrays_of_double", cat="plot"):
                arrays = ensure_arrays_of_double(x, y)
            with _tracing.zone("impl.set_data", cat="plot"):
                self._get_impl_or_raise().set_data(*arrays)

    @property
    @on_main_thread
    def data(self):
        return self._get_impl_or_raise().data()

    @data.setter
    @on_main_thread
    def data(self, data):
        self.set_data(*data)

    @property
    @on_main_thread
    def visible(self) -> bool:
        return self._get_impl_or_raise().visible()

    @visible.setter
    @on_main_thread
    def visible(self, visible):
        self._get_impl_or_raise().set_visible(visible)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("Graph(...)")
        else:
            p.text(f"Graph({self._impl})")


class ColorMap(Plottable):
    def __init__(self, impl):
        self._impl = impl
        _wire_destroyed(self, impl)

    def _on_destroyed(self):
        self._impl = None

    def _get_impl_or_raise(self):
        if self._impl is None:
            raise ValueError("The colormap does not exist anymore.")
        return self._impl

    @on_main_thread
    def set_data(self, x, y, z):
        with _tracing.zone("ColorMap.set_data", cat="plot",
                           nx=_len_safe(x), ny=_len_safe(y)):
            with _tracing.zone("ensure_arrays_of_double", cat="plot"):
                arrays = ensure_arrays_of_double(x, y, z)
            with _tracing.zone("impl.set_data", cat="plot"):
                self._get_impl_or_raise().set_data(*arrays)

    @property
    @on_main_thread
    def data(self):
        return self._get_impl_or_raise().data()

    @data.setter
    @on_main_thread
    def data(self, data):
        self.set_data(*data)

    @property
    @on_main_thread
    def visible(self) -> bool:
        return self._get_impl_or_raise().visible()

    @visible.setter
    @on_main_thread
    def visible(self, visible):
        self._get_impl_or_raise().set_visible(visible)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("ColorMap(...)")
        else:
            p.text(f"ColorMap({self._impl})")


class Histogram2D(Plottable):
    """A 2D density histogram. Bins (x, y) scatter into an x_bins x y_bins grid."""

    def __init__(self, impl):
        self._impl: _SciQLopHistogram2D = impl
        _wire_destroyed(self, impl)

    def _on_destroyed(self):
        self._impl = None

    def _get_impl_or_raise(self):
        if self._impl is None:
            raise ValueError("The histogram does not exist anymore.")
        return self._impl

    @on_main_thread
    def set_data(self, x, y):
        with _tracing.zone("Histogram2D.set_data", cat="plot", n_points=_len_safe(x)):
            with _tracing.zone("ensure_arrays_of_double", cat="plot"):
                arrays = ensure_arrays_of_double(x, y)
            with _tracing.zone("impl.set_data", cat="plot"):
                self._get_impl_or_raise().set_data(*arrays)

    @property
    @on_main_thread
    def data(self):
        return self._get_impl_or_raise().data()

    @data.setter
    @on_main_thread
    def data(self, data):
        self.set_data(*data)

    @property
    @on_main_thread
    def visible(self) -> bool:
        return self._get_impl_or_raise().visible()

    @visible.setter
    @on_main_thread
    def visible(self, visible: bool):
        self._get_impl_or_raise().set_visible(visible)

    @property
    @on_main_thread
    def z_log_scale(self) -> bool:
        return self._get_impl_or_raise().z_log_scale()

    @z_log_scale.setter
    @on_main_thread
    def z_log_scale(self, v: bool):
        self._get_impl_or_raise().set_z_log_scale(v)

    @property
    @on_main_thread
    def gradient(self):
        return self._get_impl_or_raise().gradient()

    @gradient.setter
    @on_main_thread
    def gradient(self, g):
        self._get_impl_or_raise().set_gradient(g)

    def _repr_pretty_(self, p, cycle):
        if cycle:
            p.text("Histogram2D(...)")
        else:
            p.text(f"Histogram2D({self._impl})")


def _reject_if_colormap_already_present(plot_impl) -> None:
    """A plot has a single color-scale axis, so it can host at most one
    colormap-style plottable (ColorMap, Histogram2D, Waterfall). Reject up
    front rather than silently creating a second one that fights the first
    for the color scale."""
    existing = plot_impl.plottables() or []
    for p in existing:
        if isinstance(p, _SciQLopColorMapBase):
            raise RuntimeError(
                "this plot already contains a colormap-style plottable "
                f"({type(p).__name__}); a plot can host only one. "
                "Call panel.histogram2d(...) to create a new plot instead."
            )


_MAX_HISTOGRAM_CELLS = 25_000_000


def validate_histogram_bins(x_bins: int, y_bins: int) -> None:
    if x_bins < 1 or y_bins < 1:
        raise ValueError(
            f"histogram bins must be >= 1 (got x_bins={x_bins}, y_bins={y_bins})")
    if x_bins * y_bins > _MAX_HISTOGRAM_CELLS:
        raise ValueError(
            f"histogram grid {x_bins}x{y_bins} exceeds the "
            f"{_MAX_HISTOGRAM_CELLS:,}-cell sanity cap; reduce x_bins/y_bins")


def _create_histogram2d(plot_impl, *args, name: str = "histogram",
                        x_bins: int = 100, y_bins: int = 100,
                        z_log_scale: bool = False, gradient=None) -> Histogram2D:
    validate_histogram_bins(x_bins, y_bins)
    _reject_if_colormap_already_present(plot_impl)
    if len(args) == 1 and callable(args[0]):
        impl = plot_impl.histogram2d(args[0], name=name,
                                     x_bins=x_bins, y_bins=y_bins)
    elif len(args) == 2:
        x, y = ensure_arrays_of_double(*args)
        impl = plot_impl.histogram2d(x, y, name=name,
                                     x_bins=x_bins, y_bins=y_bins)
    else:
        raise TypeError("histogram2d expects (callable,) or (x, y)")
    hist = Histogram2D(impl)
    if z_log_scale:
        hist.z_log_scale = z_log_scale
    if gradient is not None:
        hist.gradient = gradient
    return hist


def to_plottable(impl, plot=None) -> Optional[Plottable]:
    if impl is None:
        return None
    if isinstance(impl, _SciQLopHistogram2D):
        return Histogram2D(impl)
    if hasattr(impl, "gradient"):
        return ColorMap(impl)
    return Graph(impl, plot=plot)

