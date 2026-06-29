from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from yuno.attention.service import AttentionService
from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository
from yuno.interest.service import InterestService
from yuno.memory.service import MemoryMarkService


RECENT_MESSAGE_LIMIT = 12
RECENT_CHARACTER_LIMIT = 10_000


@dataclass(frozen=True)
class SpeakerReference:
    kind: str
    public_id: str
    content: str
    source: str


@dataclass(frozen=True)
class SpeakerContext:
    history: Tuple[Dict[str, str], ...]
    references: Tuple[SpeakerReference, ...] = ()


class ContextBuilder:
    """The sole assembly point for context shown to the Speaker."""

    def __init__(
        self,
        repository: ConversationRepository,
        memory: Optional[MemoryMarkService] = None,
        attention: Optional[AttentionService] = None,
        interest: Optional[InterestService] = None,
    ):
        self.repository = repository
        self.memory = memory
        self.attention = attention
        self.interest = interest

    async def build(
        self,
        stream_id: int,
        include_memory_ids: Optional[Iterable[str]] = None,
        include_attention_ids: Optional[Iterable[str]] = None,
    ) -> SpeakerContext:
        recent = await self.repository.recent(stream_id, RECENT_MESSAGE_LIMIT)
        references: List[SpeakerReference] = []
        if self.memory:
            marks = await self.memory.references_for_stream(
                stream_id, 8, include_memory_ids
            )
            references.extend(
                SpeakerReference(
                    "memory", mark.public_id, mark.content,
                    "legacy" if mark.provenance == "legacy" else "conversation",
                )
                for mark in marks
            )
        if self.attention:
            items = await self.attention.references_for_stream(
                stream_id, 8, include_attention_ids
            )
            references.extend(
                SpeakerReference("attention", item.public_id, item.text, "conversation")
                for item in items
            )
        if self.interest:
            terms = await self.interest.references_for_stream(stream_id, 8)
            references.extend(
                SpeakerReference("interest", item.public_id, item.term, "conversation")
                for item in terms
            )
        return SpeakerContext(tuple(build_speaker_history(recent)), tuple(references))


def build_speaker_history(
    messages: List[ConversationMessage],
    character_limit: int = RECENT_CHARACTER_LIMIT,
) -> List[Dict[str, str]]:
    """Build chronological model history, retaining the newest messages first."""
    selected: List[ConversationMessage] = []
    used = 0
    for message in reversed(messages):
        rendered = _render(message)
        size = len(rendered)
        if selected and used + size > character_limit:
            break
        selected.append(message)
        used += size
    selected.reverse()
    return [{"role": message.role, "content": _render(message)} for message in selected]


def _render(message: ConversationMessage) -> str:
    if message.role == "user":
        return f"{message.author_name}: {message.content}"
    return message.content
