from dataclasses import dataclass
import re
import unicodedata
from typing import List, Tuple

from yuno.attention.service import AttentionService
from yuno.interest.service import InterestService
from yuno.memory.service import MemoryMarkService


@dataclass(frozen=True)
class ReferenceSelection:
    memory_ids: Tuple[str, ...] = ()
    attention_ids: Tuple[str, ...] = ()


class ReferenceSelector:
    """Select at most a few visible fragments; it never decides whether to reply."""

    def __init__(
        self,
        memory: MemoryMarkService,
        attention: AttentionService,
        interest: InterestService,
    ):
        self.memory = memory
        self.attention = attention
        self.interest = interest

    async def select(self, stream_id: int, current_message: str) -> ReferenceSelection:
        message_parts = _parts(current_message)
        interests = await self.interest.list_for_care(stream_id, 8)
        cues = {
            _compact(item.term)
            for item in interests
            if _compact(item.term) and _compact(item.term) in _compact(current_message)
        }
        if not message_parts and not cues:
            return ReferenceSelection()
        scored: List[tuple[float, str, str]] = []
        for mark in await self.memory.repository.list_for_stream(
            stream_id, ("active",), 8
        ):
            score = _match_score(message_parts, cues, mark.content)
            if score:
                scored.append((score + mark.confidence * 0.01, "memory", mark.public_id))
        for item in await self.attention.repository.list_open_for_stream(stream_id, 8):
            score = _match_score(message_parts, cues, item.text)
            if score:
                scored.append((score + item.rank * 0.01, "attention", item.public_id))

        scored.sort(reverse=True)
        memory_ids = []
        attention_ids = []
        for _, kind, public_id in scored[:3]:
            (memory_ids if kind == "memory" else attention_ids).append(public_id)
        return ReferenceSelection(tuple(memory_ids), tuple(attention_ids))


def _match_score(message_parts: set[str], cues: set[str], candidate: str) -> float:
    normalized = _compact(candidate)
    overlap = len(message_parts & _parts(candidate))
    cue_hits = sum(1 for cue in cues if cue in normalized)
    if not cue_hits and overlap < 3:
        return 0.0
    return float(overlap + cue_hits * 3)


def _parts(value: str) -> set[str]:
    compact = _compact(value)
    parts = set()
    for size in (2, 3):
        parts.update(
            compact[index:index + size]
            for index in range(max(0, len(compact) - size + 1))
        )
    return parts


def _compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
