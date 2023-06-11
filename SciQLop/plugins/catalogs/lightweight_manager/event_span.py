from SciQLop.widgets.plots.time_span import TimeSpan
from SciQLop.widgets.plots.time_sync_panel import TimeSyncPanel
from SciQLop.backend import TimeRange
from .event import Event

from PySide6.QtCore import Slot, Signal


class EventSpan(TimeSpan):
    selected_sig = Signal(str)

    def __init__(self, event: Event, plot_panel: TimeSyncPanel, parent=None, visible=True, read_only=False, color=None):
        TimeSpan.__init__(self, time_range=event.range, plot_panel=plot_panel, parent=parent, visible=visible,
                          read_only=read_only, color=color)

        self._event = event
        self.range_changed.connect(event.set_range)
        event.color_changed.connect(self.set_color)
        event.selection_changed.connect(self._selection_changed)
        self.selection_changed.connect(self._notify_selected)

    @Slot()
    def _selection_changed(self, selected: bool):
        self.change_selection(selected)

    def _notify_selected(self, selected: bool):
        if selected:
            self.selected_sig.emit(self._event.uuid)
