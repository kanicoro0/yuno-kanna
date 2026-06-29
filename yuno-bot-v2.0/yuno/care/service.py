from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, List, Tuple

from yuno.attention.models import AttentionItem
from yuno.attention.service import AttentionService
from yuno.care.models import CareReadRequest, CareReadResult
from yuno.conversation.context import build_speaker_history
from yuno.conversation.repository import ConversationRepository
from yuno.interest.models import InterestTerm
from yuno.interest.service import InterestService, normalize_term
from yuno.memory.models import MemoryMark
from yuno.memory.service import MemoryMarkService


@dataclass(frozen=True)
class CareApplication:
    created_memory_ids: Tuple[str, ...] = ()
    created_attention_ids: Tuple[str, ...] = ()


class CareService:
    def __init__(
        self,
        conversations: ConversationRepository,
        memory: MemoryMarkService,
        attention: AttentionService,
        interest: InterestService,
    ):
        self.conversations = conversations
        self.memory = memory
        self.attention = attention
        self.interest = interest

    async def current_state(
        self, stream_id: int
    ) -> Tuple[List[MemoryMark], List[AttentionItem], List[InterestTerm]]:
        marks = await self.memory.repository.list_for_stream(
            stream_id, ("active", "pending"), 8
        )
        attention = await self.attention.repository.list_open_for_stream(stream_id, 8)
        interests = await self.interest.list_for_care(stream_id, 8)
        return marks, attention, interests

    async def build_request(
        self,
        stream_id: int,
        current_message: str,
        addressing_strength: float,
        interest_salience: float,
        state: Tuple[List[MemoryMark], List[AttentionItem], List[InterestTerm]],
    ) -> CareReadRequest:
        marks, attention, interests = state
        recent = await self.conversations.recent(stream_id, 8)
        return CareReadRequest(
            current_message=current_message[:2000],
            recent_messages=tuple(build_speaker_history(recent, 6000)),
            memory_marks=tuple({
                "public_id": item.public_id,
                "status": item.status,
                "kind": item.kind,
                "content": item.content,
            } for item in marks),
            attention_items=tuple({
                "public_id": item.public_id,
                "text": item.text,
            } for item in attention),
            interest_terms=tuple({
                "public_id": item.public_id,
                "term": item.term,
                "weight": item.weight,
            } for item in interests),
            addressing_strength=max(0.0, min(1.0, addressing_strength)),
            interest_salience=max(0.0, min(0.7, interest_salience)),
        )

    async def apply(
        self,
        stream_id: int,
        source_message_id: int,
        result: CareReadResult,
    ) -> CareApplication:
        marks = []
        for candidate in result.memory_candidates[:3]:
            mark = await self.memory.create_pending_from_care(
                stream_id, source_message_id, candidate.content,
                candidate.kind, candidate.confidence, candidate.status,
            )
            marks.append(mark.public_id)
        attention = []
        for candidate in result.attention_candidates[:3]:
            item = await self.attention.create_open(
                stream_id, candidate.text, source_message_id, rank=candidate.rank
            )
            attention.append(item.public_id)
        await self.attention.touch_many(stream_id, result.touch_attention_ids)
        await self.interest.update_from_care(stream_id, result.interest_updates)
        return CareApplication(tuple(marks), tuple(attention))


def interest_salience(content: str, terms: Iterable[InterestTerm]) -> float:
    normalized = normalize_term(content)
    matched = [item.weight for item in terms if normalize_term(item.term) in normalized]
    return min(0.7, max(matched, default=0.0))


def overlaps_attention(content: str, items: Iterable[AttentionItem]) -> bool:
    message_grams = _grams(content)
    if not message_grams:
        return False
    return any(bool(message_grams & _grams(item.text)) for item in items)


def _grams(value: str) -> set:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    compact = re.sub(r"[\W_]+", "", normalized, flags=re.UNICODE)
    return {compact[index:index + 3] for index in range(max(0, len(compact) - 2))}
