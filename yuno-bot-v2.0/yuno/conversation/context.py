from dataclasses import dataclass
from typing import Dict, List, Tuple

from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository


RECENT_MESSAGE_LIMIT = 12
RECENT_CHARACTER_LIMIT = 10_000


@dataclass(frozen=True)
class SpeakerContext:
    history: Tuple[Dict[str, str], ...]


class ContextBuilder:
    """The sole assembly point for context shown to the Speaker."""

    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    async def build(self, stream_id: int) -> SpeakerContext:
        recent = await self.repository.recent(stream_id, RECENT_MESSAGE_LIMIT)
        return SpeakerContext(tuple(build_speaker_history(recent)))


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
