from datetime import datetime, timezone
from SciQLopPlots import SciQLopPlotRange
from .icons import register_icon  # noqa: F401
from speasy.core import make_utc_datetime, AnyDateTimeType


def listify(a):
    if type(a) in (list, tuple):
        return a
    return [a]


def filter_none(a):
    return list(filter(None.__ne__, a))


class TimeRange(SciQLopPlotRange):

    def __init__(self, start: AnyDateTimeType, stop: AnyDateTimeType):
        """Create a TimeRange object. The start and stop times can be provided as Python datetime objects, timestamps, or strings."""
        super().__init__(0, 0)
        if type(start) not in (float, int):
            start = make_utc_datetime(start).timestamp()
        if type(stop) not in (float, int):
            stop = make_utc_datetime(stop).timestamp()
        self[0] = float(min(start, stop))
        self[1] = float(max(stop, start))

    @property
    def start(self):
        """The start time in seconds since the epoch."""
        return super().start()

    @start.setter
    def start(self, value: float):
        """Set the start time in seconds since the epoch."""
        assert value <= self.stop and type(value) is float
        self[0] = value

    @property
    def datetime_start(self):
        """The start time as a Python datetime object."""
        return datetime.fromtimestamp(self.start, tz=timezone.utc)

    @property
    def stop(self):
        """The stop time in seconds since the epoch."""
        return super().stop()

    @stop.setter
    def stop(self, value: float):
        """Set the stop time in seconds since the epoch."""
        assert value >= self.start and type(value) is float
        self[1] = value

    @property
    def datetime_stop(self):
        """The stop time as a Python datetime object."""
        return datetime.fromtimestamp(self.stop, tz=timezone.utc)

    def __repr__(self):
        return f"""TimeRange: {self.start}, {self.stop}
\t{self.datetime_start}, {self.datetime_stop}
        """

    def __getstate__(self):
        return self.start, self.stop

    def __setstate__(self, state):
        super().__init__(0, 0)
        self[0] = state[0]
        self[1] = state[1]
