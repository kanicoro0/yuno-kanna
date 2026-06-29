from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AttentionItem:
    id: int
    public_id: str
    stream_id: int
    source_message_id: Optional[int]
    memory_mark_id: Optional[int]
    status: str
    text: str
    rank: float
    created_at: str
    updated_at: str
    last_touched_at: Optional[str] = None
    closed_at: Optional[str] = None
    hidden_at: Optional[str] = None
