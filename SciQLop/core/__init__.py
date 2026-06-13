from datetime import datetime as datetime, timezone as timezone
from SciQLopPlots import SciQLopPlotRange as _SciQLopPlotRange
from speasy.core import make_utc_datetime as make_utc_datetime, AnyDateTimeType as AnyDateTimeType


def _to_utc_epoch(value):
    if isinstance(value, (str, datetime)):
        return make_utc_datetime(value).timestamp()
    return value


class TimeRange(_SciQLopPlotRange):
    """SciQLopPlotRange with date inputs parsed on the Python side: the C++
    (str, str) overload silently turns unparseable strings into a NaN range,
    and the datetime overload shifts by the host timezone instead of using
    UTC. Strings and datetimes go through speasy's UTC parser, which raises
    ``ValueError`` on garbage."""

    def __init__(self, *args):
        super().__init__(*(_to_utc_epoch(a) for a in args))


def listify(a):
    if type(a) in (list, tuple):
        return a
    return [a]


def filter_none(a):
    return list(filter(None.__ne__, a))
