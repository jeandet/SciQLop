from typing import List
from SciQLopPlots import QCustomPlot, QCP, QCPAxisTickerDateTime, SciQLopGraph
from PySide6.QtCore import QMimeData, Qt, QMargins, Signal
from PySide6.QtGui import QColorConstants, QColor, QPen

from ..drag_and_drop import DropHandler, DropHelper
from ...backend.products_model import Product, ParameterType
from ...backend.plot_pipeline import PlotPipeline
from ...backend.data_provider import DataProvider
from ...backend.data_provider import providers
from ...backend.enums import DataOrder
from ...backend import TimeRange
from ...mime import decode_mime
from ...mime.types import PRODUCT_LIST_MIME_TYPE, TIME_RANGE_MIME_TYPE
from .line_graph import LineGraph
from .colormap_graph import ColorMapGraph
from seaborn import color_palette


def _to_qcolor(r: float, g: float, b: float):
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def _configure_plot(plot: QCustomPlot):
    plot.setPlottingHint(QCP.phFastPolylines, True)
    plot.setInteractions(
        QCP.iRangeDrag | QCP.iRangeZoom | QCP.iSelectPlottables | QCP.iSelectAxes | QCP.iSelectLegend | QCP.iSelectItems)
    plot.legend.setVisible(True)
    date_ticker = QCPAxisTickerDateTime()
    date_ticker.setDateTimeFormat("yyyy/MM/dd \nhh:mm:ss")
    date_ticker.setDateTimeSpec(Qt.UTC)
    plot.xAxis.setTicker(date_ticker)
    plot.plotLayout().setMargins(QMargins(0, 0, 0, 0))
    plot.plotLayout().setRowSpacing(0)
    for rect in plot.axisRects():
        rect.setMargins(QMargins(0, 0, 0, 0))

    plot.setContentsMargins(0, 0, 0, 0)
    layout = plot.layout()
    if layout:
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)


class TimeSeriesPlot(QCustomPlot):
    time_range_changed = Signal(TimeRange)
    _time_range: TimeRange = TimeRange(0., 0.)

    def __init__(self, parent=None):
        QCustomPlot.__init__(self, parent)
        self.setMinimumHeight(300)
        self._drop_helper = DropHelper(widget=self,
                                       handlers=[
                                           DropHandler(mime_type=PRODUCT_LIST_MIME_TYPE,
                                                       callback=self._plot),
                                           DropHandler(mime_type=TIME_RANGE_MIME_TYPE,
                                                       callback=self._set_time_range)])
        self._pipeline: List[PlotPipeline] = []
        self._palette = color_palette()
        self._palette_index = 0
        _configure_plot(self)
        self.xAxis.rangeChanged.connect(lambda range: self.time_range_changed.emit(TimeRange(range.lower, range.upper)))

    def generate_colors(self, count: int) -> List[QColor]:
        index = self._palette_index
        self._palette_index += count
        return [
            _to_qcolor(*self._palette[(index + i) % len(self._palette)]) for i in range(count)
        ]

    def _plot(self, mime_data: QMimeData) -> bool:
        products: List[Product] = decode_mime(mime_data)
        for product in products:
            self.plot(product)
        return True

    def _set_time_range(self, mime_data: QMimeData) -> bool:
        self.time_range = decode_mime(mime_data, [TIME_RANGE_MIME_TYPE])
        return True

    @property
    def time_range(self) -> TimeRange:
        return TimeRange(self.xAxis.range().lower, self.xAxis.range().upper)

    @time_range.setter
    def time_range(self, time_range: TimeRange):
        if self._time_range != time_range:
            print("Setting xAxis range")
            self.xAxis.setRange(time_range.start, time_range.stop)
            self.replot(QCustomPlot.rpQueuedReplot)

    def plot(self, product: Product):
        if product.parameter_type in (ParameterType.VECTOR, ParameterType.MULTICOMPONENT, ParameterType.SCALAR):
            self.add_multi_line_graph(providers[product.provider], product.uid,
                                      components=product.metadata.get('components') or [product.name])
        elif product.parameter_type == ParameterType.SPECTROGRAM:
            self.add_colormap_graph(providers[product.provider], product.uid)

    def add_multi_line_graph(self, provider: DataProvider, product: str, components: List[str]):
        graph = LineGraph(self, provider.data_order)
        self.xAxis.rangeChanged.connect(lambda range: graph.xRangeChanged.emit(TimeRange(range.lower, range.upper)))
        pipeline = PlotPipeline(graph=graph, provider=provider, product=product, time_range=self.time_range)
        self._pipeline.append(pipeline)

    def add_colormap_graph(self, provider: DataProvider, product: str):
        graph = ColorMapGraph(self, self.addColorMap(self.xAxis, self.yAxis))
        self.xAxis.rangeChanged.connect(lambda range: graph.xRangeChanged.emit(TimeRange(range.lower, range.upper)))
        pipeline = PlotPipeline(graph=graph, provider=provider, product=product, time_range=self.time_range)
        self._pipeline.append(pipeline)
