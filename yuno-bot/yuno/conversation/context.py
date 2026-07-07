from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from yuno.care_marks.service import CareMarkService
from yuno.conversation.models import ConversationMessage
from yuno.conversation.repository import ConversationRepository


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
    route_reason: Optional[str] = None


class ContextBuilder:
    '''The sole assembly point for context shown to the Speaker.'''

    def __init__(
        self,
        repository: ConversationRepository,
        care_marks: Optional[CareMarkService] = None,
    ):
        self.repository = repository
        self.care_marks = care_marks

    async def build(
        self,
        stream_id: int,
        include_care_mark_ids: Iterable[str] = (),
        route_reason: Optional[str] = None,
    ) -> SpeakerContext:
        recent = await self.repository.recent(stream_id, RECENT_MESSAGE_LIMIT)
        references: List[SpeakerReference] = []
        if self.care_marks:
            for public_id in dict.fromkeys(include_care_mark_ids):
                if len(references) >= REFERENCE_LIMIT:
                    break
                mark = await self.care_marks.get_by_public_id(public_id)
                if (
                    mark
                    and mark.stream_id == stream_id
                    and _speaker_visible(mark.kind, mark.status)
                ):
                    references.append(SpeakerReference(
                        kind=mark.kind,
                        public_id=mark.public_id,
                        content=mark.text,
                        source='conversation',
                    ))
        return SpeakerContext(
            tuple(build_speaker_history(recent)),
            tuple(references),
            route_reason,
        )


def _speaker_visible(kind: str, status: str) -> bool:
    return (
        kind == 'memory' and status == 'active'
    ) or (
        kind == 'attention' and status == 'open'
    )


def build_speaker_history(
    messages: List[ConversationMessage],
    character_limit: int = RECENT_CHARACTER_LIMIT,
) -> List[Dict[str, str]]:
    '''Build chronological model history, retaining the newest messages first.'''
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
    return [
        {'role': message.role, 'content': _render(message)}
        for message in selected
    ]


def _render(message: ConversationMessage) -> str:
    if message.role == 'user':
        return f'{message.author_name}: {message.content}'
    return message.content
