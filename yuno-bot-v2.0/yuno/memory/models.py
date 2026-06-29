from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class MemoryMark:
    id: int
    public_id: str
    stream_id: Optional[int]
    source_message_id: Optional[int]
    kind: str
    status: str
    content: str
    confidence: float
    provenance: str
    created_at: str
    updated_at: str
    hidden_at: Optional[str] = None
    legacy_source_id: Optional[str] = None
    legacy_import_batch_id: Optional[str] = None
