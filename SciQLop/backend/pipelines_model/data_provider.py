from typing import Tuple, Optional, List

import numpy as np

from SciQLop.backend.enums import DataOrder
from speasy.products import SpeasyVariable, VariableAxis
from speasy.core import datetime64_to_epoch

providers = {}


def _ensure_float64_and_C(v):
    if v.dtype != np.float64:
        v= v.astype(np.float64)
    if not v.flags.c_contiguous:
        v = np.ascontiguousarray(v)
    return v


def _sort_axis_by_time(axis: VariableAxis, sorted_indices)-> VariableAxis:
    if axis.is_time_dependent:
        axis.values[:] = axis.values[sorted_indices]
        return axis

def _sort_variable_by_time(variable: SpeasyVariable) -> SpeasyVariable:
    sorted_indices = np.argsort(variable.time)
    for i in range(len(variable.axes)):
        _sort_axis_by_time(variable.axes[i], sorted_indices)
    variable.values[:] = variable.values[sorted_indices]
    return variable



class DataProvider:
    def __init__(self, name: str, data_order: DataOrder = DataOrder.X_FIRST, cacheable: bool = False):
        global providers
        providers[name] = self
        self._name = name
        self._data_order = data_order
        self._cacheable = cacheable

    def __del__(self):
        global providers
        if providers is not None:
            providers.pop(self._name)

    @property
    def name(self) -> str:
        return self._name

    @property
    def data_order(self) -> DataOrder:
        return self._data_order

    @property
    def cacheable(self) -> bool:
        return self._cacheable

    def labels(self, node) -> List[str]:
        pass

    def _get_data(self, node, start, stop) -> List[np.ndarray]:
        try:
            v = self.get_data(node, start, stop)
            if v is None:
                return []
            if isinstance(v, list) or isinstance(v, tuple):
                return v
            if not np.all(np.diff(v.time) >= 0) :
                v=_sort_variable_by_time(v)
            time = datetime64_to_epoch(v.time)
            if len(v.axes) == 1:
                return [time, _ensure_float64_and_C(v.values)]
            return [time, _ensure_float64_and_C(v.axes[1].values), _ensure_float64_and_C(v.values)]
        except Exception as e:
            print(e)
            return []

    def get_data(self, node, start, stop) -> Optional[SpeasyVariable]:
        pass
