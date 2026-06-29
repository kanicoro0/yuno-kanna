from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from yuno.attention.service import AttentionService
from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository
from yuno.interest.service import InterestService
from yuno.memory.service import MemoryMarkService


RECENT_MESSAGE_LIMIT = 6
RECENT_CHARACTER_LIMIT = 10_000
REFERENCE_LIMIT = 3


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
        include_memory_ids: Iterable[str] = (),
        include_attention_ids: Iterable[str] = (),
    ) -> SpeakerContext:
        recent = await self.repository.recent(stream_id, RECENT_MESSAGE_LIMIT)
        references: List[SpeakerReference] = []
        for public_id in dict.fromkeys(include_memory_ids):
            if len(references) >= REFERENCE_LIMIT or not self.memory:
                break
            mark = await self.memory.repository.get_by_public_id(public_id)
            if mark and mark.stream_id == stream_id and mark.status == "active":
                references.append(SpeakerReference(
                    "memory", mark.public_id, mark.content,
                    "legacy" if mark.provenance == "legacy" else "conversation",
                ))
        for public_id in dict.fromkeys(include_attention_ids):
            if len(references) >= REFERENCE_LIMIT or not self.attention:
                break
            item = await self.attention.repository.get_by_public_id(public_id)
            if item and item.stream_id == stream_id and item.status == "open":
                references.append(SpeakerReference(
                    "attention", item.public_id, item.text, "conversation"
                ))
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
