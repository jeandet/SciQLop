"""SearchDomain contract: describes a searchable topic/corpus for the smart
search registry. Deliberately plain (path_key, raw_text) pairs rather than a
live model-node reference, so index/query never need to touch a
Shiboken-wrapped C++ object on the hot per-query path."""
from typing import Iterable, NamedTuple, Protocol


class NodeSnapshot(NamedTuple):
    path_key: str
    raw_text: str


class SearchDomain(Protocol):
    name: str

    def snapshot(self) -> Iterable[NodeSnapshot]:
        ...
