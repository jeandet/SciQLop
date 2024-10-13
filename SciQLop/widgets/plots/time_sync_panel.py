import sys
from datetime import datetime
from gc import callbacks
from typing import Optional, List, Any

import numpy as np
from PySide6.QtCore import QMimeData, Signal, QMargins
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QScrollArea
from SciQLopPlots import SciQLopMultiPlotPanel, PlotDragNDropCallback, SciQLopPlotInterface, ProductsModel, SciQLopPlot, \
    ParameterType, GraphType

from SciQLop.backend.icons import register_icon
from ...backend import TimeRange
from ...backend import listify
from ...backend import sciqlop_logging
from ...backend.pipelines_model.data_provider import providers
from ...backend.property import SciQLopProperty
from ...mime import decode_mime
from ...mime.types import PRODUCT_LIST_MIME_TYPE, TIME_RANGE_MIME_TYPE
from .palette import Palette, make_color_list

log = sciqlop_logging.getLogger(__name__)

register_icon("QCP", QIcon("://icons/QCP.png"))


class _plot_product_callback:
    def __init__(self, provider, node):
        self.provider = provider
        self.node = node

    def __call__(self, start, stop):
        try:
            return self.provider._get_data(self.node, start, stop)
        except Exception as e:
            log.error(f"Error getting data for {self.node}: {e}")
            return []


def _plot_product(plot: SciQLopPlot, product: Any):
    if isinstance(product, list):
        node = ProductsModel.node(product)
        if node is not None:
            provider = providers.get(node.provider())
            if provider is not None:
                callback = _plot_product_callback(provider, node)
                if node.parameter_type() in (ParameterType.Scalar, ParameterType.Vector, ParameterType.Multicomponents):
                    labels = listify(provider.labels(node))
                    graph = plot.plot(callback, labels=labels)
                    graph.set_name(node.name())
                elif node.parameter_type() == ParameterType.Spectrogram:
                    plot.plot(callback, name=node.name(), graph_type=GraphType.ColorMap, y_log_scale=True,
                              z_log_scale=True)


class ProductDnDCallback(PlotDragNDropCallback):
    def __init__(self, parent):
        super().__init__(PRODUCT_LIST_MIME_TYPE, True, parent)

    def call(self, plot, mime_data: QMimeData):
        for product in decode_mime(mime_data):
            node = ProductsModel.node(product)
            if node is not None:
                _plot_product(plot, product)


class TimeRangeDnDCallback(PlotDragNDropCallback):
    def __init__(self, parent):
        super().__init__(TIME_RANGE_MIME_TYPE, False, parent)

    def call(self, plot, mime_data: QMimeData):
        time_range = decode_mime(mime_data)
        plot.time_axis().set_range(time_range)


class TimeSyncPanel(SciQLopMultiPlotPanel):

    def __init__(self, name: str, parent=None, time_range: Optional[TimeRange] = None):
        super().__init__(parent, synchronize_x=False, synchronize_time=True)
        self.setObjectName(name)
        self.setWindowTitle(name)
        self._parent_node = None
        self._product_plot_callback = ProductDnDCallback(self)
        self._time_range_plot_callback = TimeRangeDnDCallback(self)
        self.add_accepted_mime_type(self._product_plot_callback)
        self.add_accepted_mime_type(self._time_range_plot_callback)
        self.set_color_palette(make_color_list(Palette()))
        if time_range is not None:
            self.time_range = time_range

    @SciQLopProperty(TimeRange)
    def time_range(self) -> TimeRange:
        return TimeRange(*self.time_axis_range())

    @time_range.setter
    def time_range(self, time_range: TimeRange):
        self.set_time_axis_range(time_range.start, time_range.stop)

    def __repr__(self):
        return f"TimeSyncPanel: {self.name}"

    @SciQLopProperty(str)
    def icon(self) -> str:
        return "QCP"
