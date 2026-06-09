import inspect
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Callable, Optional, Union, get_args, get_origin, get_type_hints

ProductPath = Union[str, list]
DependencyTarget = Union[ProductPath, object, Callable[[float, float], Any]]


@dataclass(frozen=True, slots=True)
class Depends:
    """Signature marker declaring a virtual-product dependency.

    Used as ``Annotated[SpeasyVariable, Depends(target, pad=...)]``. ``target`` is a
    product path (``"a//b"`` or ``["a", "b"]``), a ``VirtualProduct`` handle, or a
    ``callable(start, stop)``. ``pad`` widens the resolution window symmetrically
    (seconds as ``float`` or ``datetime.timedelta``)."""
    target: DependencyTarget
    pad: Optional[Union[float, timedelta]] = None


@dataclass(frozen=True, slots=True)
class DependsSpec:
    name: str
    target: DependencyTarget
    pad: float  # seconds, 0.0 when unset


def _pad_seconds(pad) -> float:
    if pad is None:
        return 0.0
    if isinstance(pad, timedelta):
        return pad.total_seconds()
    return float(pad)


def depends_marker(annotation) -> Optional[Depends]:
    if get_origin(annotation) is Annotated:
        for extra in get_args(annotation)[1:]:
            if isinstance(extra, Depends):
                return extra
    return None


def extract_dependencies_from_callback(callback) -> list[DependsSpec]:
    try:
        hints = get_type_hints(callback, include_extras=True)
    except (NameError, TypeError):
        hints = {}
    sig = inspect.signature(callback)
    specs = []
    for name, param in sig.parameters.items():
        marker = depends_marker(hints.get(name, param.annotation))
        if marker is not None:
            specs.append(DependsSpec(name=name, target=marker.target,
                                     pad=_pad_seconds(marker.pad)))
    return specs
