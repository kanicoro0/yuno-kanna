import asyncio
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

from yuno.care.safety import looks_sensitive
from yuno.care_marks.models import CareMark
from yuno.care_marks.service import CARE_MARK_STATUSES, CareMarkService
from yuno.conversation.models import ConversationMessage, Stream
from yuno.conversation.repository import ConversationRepository


CARE_MARK_KINDS = ('memory', 'attention')
CARE_MARK_STATUS_NAMES = (
    'draft', 'active', 'open', 'closed', 'hidden'
)


@dataclass(frozen=True)
class SourceMarkChange:
    mark: CareMark
    outcome: str


class CareMarkCommandService:
    def __init__(
        self,
        conversations: ConversationRepository,
        care_marks: CareMarkService,
    ):
        self.conversations = conversations
        self.care_marks = care_marks
        self._source_mark_lock = asyncio.Lock()

    async def stream(
        self, channel_id: str, guild_id: Optional[str], create: bool = False
    ) -> Optional[Stream]:
        existing = await self.conversations.get_stream_by_channel_id(channel_id)
        if existing or not create:
            return existing
        return await self.conversations.get_or_create_stream(
            'dm' if guild_id is None else 'channel',
            channel_id,
            guild_id,
        )

    async def list_marks(
        self,
        channel_id: str,
        guild_id: Optional[str],
        kind: str = 'all',
        status: str = 'visible',
        limit: int = 10,
    ) -> List[CareMark]:
        stream = await self.stream(channel_id, guild_id)
        if stream is None:
            return []
        if kind != 'all':
            self._validate_kind(kind)
        kinds = CARE_MARK_KINDS if kind == 'all' else (kind,)
        statuses = self._statuses(status)
        return await self.care_marks.list_for_stream(
            stream.id,
            kinds,
            statuses,
            _limit(limit),
        )

    async def add_mark(
        self,
        channel_id: str,
        guild_id: Optional[str],
        kind: str,
        text: str,
        status: Optional[str] = None,
        source_message_id: Optional[int] = None,
    ) -> CareMark:
        self._validate_kind(kind)
        selected_status = status or (
            'draft' if kind == 'memory' else 'open'
        )
        if (
            kind == 'memory'
            and selected_status == 'active'
            and looks_sensitive(text)
        ):
            selected_status = 'draft'
        self._validate_status(kind, selected_status)
        stream = await self.stream(channel_id, guild_id, True)
        return await self.care_marks.create(
            stream.id,
            kind,
            selected_status,
            text,
            source_message_id=source_message_id,
        )

    async def add_mark_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
        kind: str,
    ) -> Optional[CareMark]:
        change = await self.reuse_mark_from_message(
            channel_id, discord_message_id, kind
        )
        return change.mark if change else None

    async def marks_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
        kind: str,
    ) -> Optional[List[CareMark]]:
        context = await self._message_context(channel_id, discord_message_id)
        if context is None:
            return None
        stream, message = context
        return await self.care_marks.list_for_source(
            stream.id, message.id, kind
        )

    async def reuse_mark_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
        kind: str,
    ) -> Optional[SourceMarkChange]:
        self._validate_kind(kind)
        async with self._source_mark_lock:
            return await self._reuse_mark_from_message(
                channel_id, discord_message_id, kind
            )

    async def _reuse_mark_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
        kind: str,
    ) -> Optional[SourceMarkChange]:
        context = await self._message_context(channel_id, discord_message_id)
        if context is None:
            return None
        stream, message = context
        marks = await self.care_marks.list_for_source(
            stream.id, message.id, kind
        )
        reusable_statuses = (
            {'draft', 'active'} if kind == 'memory' else {'open'}
        )
        reusable = next((
            mark for mark in marks if mark.status in reusable_statuses
        ), None)
        if reusable is not None:
            return SourceMarkChange(reusable, 'existing')
        if marks:
            target_status = 'draft' if kind == 'memory' else 'open'
            reopened = await self.care_marks.update(
                marks[0].public_id, status=target_status
            )
            if reopened is not None:
                return SourceMarkChange(reopened, 'reopened')
        created = await self.add_mark(
            channel_id,
            stream.discord_guild_id,
            kind,
            message.content,
            source_message_id=message.id,
        )
        return SourceMarkChange(created, 'created')

    async def close_attention_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
    ) -> Optional[SourceMarkChange]:
        async with self._source_mark_lock:
            return await self._close_attention_from_message(
                channel_id, discord_message_id
            )

    async def _close_attention_from_message(
        self,
        channel_id: str,
        discord_message_id: str,
    ) -> Optional[SourceMarkChange]:
        marks = await self.marks_from_message(
            channel_id, discord_message_id, 'attention'
        )
        if marks is None:
            return None
        newest_open = next((
            mark for mark in marks if mark.status == 'open'
        ), None)
        if newest_open is None:
            return None
        closed = await self.care_marks.update(
            newest_open.public_id, status='closed'
        )
        return SourceMarkChange(closed, 'closed') if closed else None

    async def _message_context(
        self,
        channel_id: str,
        discord_message_id: str,
    ) -> Optional[Tuple[Stream, ConversationMessage]]:
        stream = await self.conversations.get_stream_by_channel_id(channel_id)
        message = await self.conversations.find_by_discord_message_id(
            discord_message_id
        )
        if (
            stream is None
            or message is None
            or message.stream_id != stream.id
        ):
            return None
        return stream, message

    async def set_status(
        self,
        channel_id: str,
        public_id: str,
        status: str,
    ) -> Optional[CareMark]:
        stream = await self.conversations.get_stream_by_channel_id(channel_id)
        mark = await self.care_marks.get_by_public_id(public_id)
        if stream is None or mark is None or mark.stream_id != stream.id:
            return None
        self._validate_status(mark.kind, status)
        return await self.care_marks.update(public_id, status=status)

    @staticmethod
    def _statuses(status: str) -> Iterable[str]:
        if status == 'all':
            return CARE_MARK_STATUS_NAMES
        if status == 'visible':
            return ('active', 'open')
        if status not in CARE_MARK_STATUS_NAMES:
            raise ValueError('invalid care mark status filter')
        return (status,)

    @staticmethod
    def _validate_kind(kind: str) -> None:
        if kind not in CARE_MARK_KINDS:
            raise ValueError('invalid care mark kind')

    @staticmethod
    def _validate_status(kind: str, status: str) -> None:
        CareMarkCommandService._validate_kind(kind)
        if status not in CARE_MARK_STATUSES[kind]:
            raise ValueError(f'invalid status for {kind} care mark')


def _limit(value: int) -> int:
    return max(1, min(20, int(value)))
