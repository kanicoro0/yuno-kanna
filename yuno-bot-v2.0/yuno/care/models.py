from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class MemoryCandidate:
    content: str
    kind: str
    status: str
    confidence: float


@dataclass(frozen=True)
class AttentionCandidate:
    text: str
    rank: float


@dataclass(frozen=True)
class InterestUpdate:
    term: str
    weight: float


@dataclass(frozen=True)
class CareReadRequest:
    current_message: str
    recent_messages: Tuple[Dict[str, str], ...]
    memory_marks: Tuple[Dict[str, Any], ...]
    attention_items: Tuple[Dict[str, Any], ...]
    interest_terms: Tuple[Dict[str, Any], ...]
    addressing_strength: float
    interest_salience: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_message": self.current_message,
            "recent_messages": list(self.recent_messages),
            "memory_marks": list(self.memory_marks),
            "attention_items": list(self.attention_items),
            "interest_terms": list(self.interest_terms),
            "addressing_strength": self.addressing_strength,
            "interest_salience": self.interest_salience,
        }


@dataclass(frozen=True)
class CareReadResult:
    wants_to_speak: bool = False
    should_speak: bool = False
    memory_candidates: Tuple[MemoryCandidate, ...] = ()
    attention_candidates: Tuple[AttentionCandidate, ...] = ()
    touch_attention_ids: Tuple[str, ...] = ()
    interest_updates: Tuple[InterestUpdate, ...] = ()
    include_memory_ids: Tuple[str, ...] = ()
    include_attention_ids: Tuple[str, ...] = ()
