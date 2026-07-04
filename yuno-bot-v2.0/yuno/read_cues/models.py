from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReadCue:
    id: int
    care_mark_id: int
    term: str
    normalized_term: str
    weight: float
    status: str
    created_at: str
    updated_at: str
    last_touched_at: Optional[str] = None
