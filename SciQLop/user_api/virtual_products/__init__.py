from speasy import SpeasyVariable
from typing import Callable, List, Optional
from enum import Enum
from SciQLop.backend.pipelines_model.easy_provider import EasyVector as _EasyVector, EasyScalar as _EasyScalar, \
    EasySpectrogram as _EasySpectrogram, EasyMultiComponent as _EasyMultiComponent


class VirtualProductType(Enum):
    Vector = 0
    Scalar = 1
    MultiComponent = 2
    Spectrogram = 3


class VirtualProduct:
    def __init__(self, path: str, callback: Callable[[float, float], SpeasyVariable], product_type: VirtualProductType):
        self._path = path
        self._callback = callback
        self._product_type = product_type

    @property
    def path(self) -> str:
        return self._path

    @property
    def product_type(self) -> VirtualProductType:
        return self._product_type


class VirtualScalar(VirtualProduct):
    def __init__(self, path: str, callback: Callable[[float, float], SpeasyVariable], label: str):
        super(VirtualScalar, self).__init__(path, callback, VirtualProductType.Scalar)
        self._impl = _EasyScalar(path, callback, component_name=label, metadata={})


class VirtualVector(VirtualProduct):
    def __init__(self, path: str, callback: Callable[[float, float], SpeasyVariable], labels: List[str]):
        super(VirtualVector, self).__init__(path, callback, VirtualProductType.Vector)
        self._impl = _EasyVector(path, callback, components_names=labels, metadata={})


class VirtualMultiComponent(VirtualProduct):
    def __init__(self, path: str, callback: Callable[[float, float], SpeasyVariable], labels: List[str]):
        super(VirtualMultiComponent, self).__init__(path, callback, VirtualProductType.MultiComponent)
        self._impl = _EasyMultiComponent(path, callback, components_names=labels, metadata={})


class VirtualSpectrogram(VirtualProduct):
    def __init__(self, path: str, callback: Callable[[float, float], SpeasyVariable]):
        super(VirtualSpectrogram, self).__init__(path, callback, VirtualProductType.Spectrogram)
        self._impl = _EasySpectrogram(path, callback, metadata={})


def create_virtual_product(path: str, callback: Callable[[float, float], SpeasyVariable],
                           product_type: VirtualProductType, labels: Optional[List[str]] = None) -> VirtualProduct:
    if product_type == VirtualProductType.Scalar:
        assert labels is not None and len(labels) == 1
        return VirtualScalar(path, callback, label=labels[0])
    elif product_type == VirtualProductType.Vector:
        assert labels is not None and len(labels) == 3
        return VirtualVector(path, callback, labels=labels)
    elif product_type == VirtualProductType.MultiComponent:
        assert labels is not None
        return VirtualMultiComponent(path, callback, labels=labels)
    elif product_type == VirtualProductType.Spectrogram:
        return VirtualSpectrogram(path, callback)
