import hashlib
import logging
from typing import Iterable, Optional

import discord

from yuno.care_marks.models import CareMark
from yuno.conversation.repository import ConversationRepository


logger = logging.getLogger(__name__)

# These are shared palettes, not emoji-to-meaning tables. Kind, status, mark
# text, and local source text only nudge a stable choice within one pool:
# one pool for marks that now stand, one for marks quietly put to rest.
_CALM_REACTIONS = ('🌙', '🫧', '🌿', '✨', '🕯️', '☁️', '🪶', '🌱')
_SETTLED_REACTIONS = ('🍂', '💤', '🌙', '🕊️')


def pick_care_mark_reaction(
    mark: CareMark,
    source_text: str,
) -> Optional[str]:
    if not source_text.strip():
        return None
    if _is_standing(mark):
        pool = _CALM_REACTIONS
    elif _is_settled(mark):
        pool = _SETTLED_REACTIONS
    else:
        return None
    seed = '\0'.join((mark.kind, mark.status, mark.text, source_text))
    digest = hashlib.blake2s(seed.encode('utf-8'), digest_size=2).digest()
    index = int.from_bytes(digest, 'big') % len(pool)
    return pool[index]


def _is_standing(mark: CareMark) -> bool:
    return (
        mark.kind == 'memory' and mark.status == 'active'
        or mark.kind == 'attention' and mark.status == 'open'
    )


def _is_settled(mark: CareMark) -> bool:
    return mark.status in ('closed', 'hidden')


class CareReactionSurface:
    def __init__(self, resolver: Optional['CareReactionTargetResolver'] = None):
        self.resolver = resolver

    async def add_for_marks(
        self,
        source: discord.Message,
        marks: Iterable[CareMark],
    ) -> None:
        all_marks = tuple(marks)
        standing = tuple(sorted(
            (mark for mark in all_marks if _is_standing(mark)),
            key=lambda mark: mark.id,
        ))
        if standing:
            target = source
            if self.resolver is not None:
                try:
                    target = await self.resolver.resolve(source, standing)
                except Exception:
                    logger.exception(
                        'Care reaction target resolution failed; using source'
                    )
                    target = source
            await self._react_once(target, standing)
            return
        # Marks put to rest this turn react on the current message: the
        # request itself gets the quiet acknowledgment, not the old spot
        # where the mark was born.
        settled = tuple(sorted(
            (mark for mark in all_marks if _is_settled(mark)),
            key=lambda mark: mark.id,
        ))
        if settled:
            await self._react_once(source, settled)

    @staticmethod
    async def _react_once(
        target: discord.Message,
        selected: Iterable[CareMark],
    ) -> None:
        add_reaction = getattr(target, 'add_reaction', None)
        if not callable(add_reaction):
            return
        # A quiet surface: at most one reaction per batch. The loop only
        # walks newest-first past marks whose seed yields no emoji; the
        # first attempted reaction ends it, even when Discord rejects it.
        for mark in reversed(tuple(selected)):
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
