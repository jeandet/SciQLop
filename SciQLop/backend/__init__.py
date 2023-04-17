from datetime import datetime

from .products_model.product_node import ProductNode as Product


def listify(a):
    if type(a) in (list, tuple):
        return a
    return [a]


class TimeRange:
    __slots__ = ["_start", "_stop"]

    def __init__(self, start: float, stop: float):
        self._start = start
        self._stop = stop

    @property
    def start(self):
        return self._start

    @property
    def datetime_start(self):
        return datetime.utcfromtimestamp(self._start)

    @property
    def stop(self):
        return self._stop

    @property
    def datetime_stop(self):
        return datetime.utcfromtimestamp(self._stop)

    def __mul__(self, other):
        if type(other) is float:
            new_dt = (self._stop - self._start) * other / 2.
            center = (self._start + self._stop) / 2.
            return TimeRange(center - new_dt, center + new_dt)
        else:
            return NotImplemented

    def __rmul__(self, other):
        return self.__mul__(other)

    def overlaps(self, other: "TimeRange"):
        return max(self._start, other._start) <= min(self._stop, other._stop)

    def __repr__(self):
        return f"""TimeRange: {self._start}, {self._stop}
\t{self.datetime_start}, {self.datetime_stop}
        """
