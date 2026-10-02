from typing import Protocol, runtime_checkable, Any
from app.models import Meeting

@runtime_checkable
class MeetingAdapter(Protocol):
    def load(self, source: Any) -> Meeting:
        ...
