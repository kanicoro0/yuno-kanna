import hashlib
import logging
from typing import Iterable, Optional

import discord

from yuno.care_marks.models import CareMark
from yuno.conversation.repository import ConversationRepository


logger = logging.getLogger(__name__)

# This is a shared palette, not an emoji-to-meaning table. Kind, status, mark
# text, and local source text only nudge a stable choice within the same pool.
_CALM_REACTIONS = ('🌙', '🫧', '🌿', '✨', '🕯️', '☁️', '🪶', '🌱')


def pick_care_mark_reaction(
    mark: CareMark,
    source_text: str,
) -> Optional[str]:
    if not source_text.strip():
        return None
    if not (
        mark.kind == 'memory' and mark.status == 'active'
        or mark.kind == 'attention' and mark.status == 'open'
    ):
        return None
    seed = '\0'.join((mark.kind, mark.status, mark.text, source_text))
    digest = hashlib.blake2s(seed.encode('utf-8'), digest_size=2).digest()
    index = int.from_bytes(digest, 'big') % len(_CALM_REACTIONS)
    return _CALM_REACTIONS[index]


class CareReactionSurface:
    def __init__(self, resolver: Optional['CareReactionTargetResolver'] = None):
        self.resolver = resolver

    async def add_for_marks(
        self,
        source: discord.Message,
        marks: Iterable[CareMark],
    ) -> None:
        selected = tuple(sorted(
            (
                mark for mark in marks
                if mark.kind == 'memory' and mark.status == 'active'
                or mark.kind == 'attention' and mark.status == 'open'
            ),
            key=lambda mark: mark.id,
        ))
        if not selected:
            return
        target = source
        if self.resolver is not None:
            try:
                target = await self.resolver.resolve(source, selected)
            except Exception:
                logger.exception(
                    'Care reaction target resolution failed; using source'
                )
                target = source
        add_reaction = getattr(target, 'add_reaction', None)
        if not callable(add_reaction):
            return
        for mark in reversed(selected):
            emoji = pick_care_mark_reaction(mark, target.content)
            if emoji is None:
                continue
            try:
                await add_reaction(emoji)
            except Exception:
                logger.exception(
                    'CareMark persisted but Discord reaction failed'
                )
            return


class CareReactionTargetResolver:
    def __init__(self, conversations: ConversationRepository):
        self.conversations = conversations

    async def resolve(
        self,
        fallback: discord.Message,
        marks: Iterable[CareMark],
    ) -> discord.Message:
        selected = max(
            (
                mark for mark in marks
                if mark.source_message_id is not None
            ),
            key=lambda mark: mark.id,
            default=None,
        )
        if selected is None:
            return fallback
        record = await self.conversations.get_message(
            selected.source_message_id
        )
        if record is None or record.stream_id != selected.stream_id:
            return fallback
        if str(getattr(fallback, 'id', '')) == record.discord_message_id:
            return fallback
        fetch_message = getattr(fallback.channel, 'fetch_message', None)
        if not callable(fetch_message):
            return fallback
        try:
            return await fetch_message(int(record.discord_message_id))
        except Exception:
            logger.debug(
                'Care reaction target unavailable; using source',
                exc_info=True,
            )
            return fallback
