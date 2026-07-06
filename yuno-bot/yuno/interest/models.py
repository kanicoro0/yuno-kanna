from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InterestTerm:
    id: int
    public_id: str
    stream_id: int
    term: str
    weight: float
    status: str
    source: str
    created_at: str
    updated_at: str
    last_touched_at: Optional[str] = None
