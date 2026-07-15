from dataclasses import dataclass
from typing import Callable, Any

TargetResolver = Callable[[Any, dict], object | None]
CompletionResolver = Callable[[Any, dict], object | None]


@dataclass(frozen=True)
class TourStep:
    step_id: str
    title: str
    body: str
    resolver: TargetResolver
    completion: CompletionResolver | None = None
    poll: bool = False
    timeout_s: float | None = None
    timeout_message: str | None = None


@dataclass(frozen=True)
class Tour:
    id: str
    title: str
    description: str
    steps: list[TourStep]
