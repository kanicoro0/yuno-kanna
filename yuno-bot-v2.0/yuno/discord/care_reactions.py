import hashlib
import logging
from typing import Iterable, Optional

import discord

from yuno.care_marks.models import CareMark


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
    async def add_for_marks(
        self,
        source: discord.Message,
        marks: Iterable[CareMark],
    ) -> None:
        add_reaction = getattr(source, 'add_reaction', None)
        if not callable(add_reaction):
            return
        for mark in reversed(tuple(marks)):
            emoji = pick_care_mark_reaction(mark, source.content)
            if emoji is None:
                continue
            try:
                await add_reaction(emoji)
            except Exception:
                logger.exception(
                    'CareMark persisted but Discord reaction failed'
                )
            return
