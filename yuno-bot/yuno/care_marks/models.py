from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CareMark:
    id: int
    public_id: str
    stream_id: int
    source_message_id: Optional[int]
    kind: str
    status: str
    text: str
    created_at: str
    updated_at: str
    last_touched_at: Optional[str] = None
