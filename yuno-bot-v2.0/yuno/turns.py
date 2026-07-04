import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from yuno.conversation.models import ConversationMessage


TURN_DEBOUNCE_SECONDS = 2.0


@dataclass(frozen=True)
class PipelineTurn:
    """The unit selected for reading after its source messages are stored."""

    stream_id: int
    author_id: str
    content: str
    source_user_message_ids: Tuple[int, ...]
    should_reply: bool
    route_reason: str
    reply_mode: str
    reply_to_discord_message_id: Optional[str]

    @classmethod
    def from_stored_message(
        cls,
        message: ConversationMessage,
        *,
        should_reply: bool,
        route_reason: str,
        reply_mode: str,
        reply_to_discord_message_id: Optional[str],
    ) -> "PipelineTurn":
        if message.role != "user":
            raise ValueError("a user turn must come from a stored user message")
        return cls(
            stream_id=message.stream_id,
            author_id=message.author_id,
            content=message.content,
            source_user_message_ids=(message.id,),
            should_reply=should_reply,
            route_reason=route_reason,
            reply_mode=reply_mode,
            reply_to_discord_message_id=reply_to_discord_message_id,
        )

    @property
    def single_source_user_message_id(self) -> int:
        if len(self.source_user_message_ids) != 1:
            raise ValueError("current CareService attribution requires one source message")
        return self.source_user_message_ids[0]

    @property
    def care_source_user_message_id(self) -> int:
        """Compatibility attribution until CareService supports multiple sources."""
        if not self.source_user_message_ids:
            raise ValueError("a turn must have at least one source message")
        return self.source_user_message_ids[-1]

    def can_merge(self, newer: "PipelineTurn") -> bool:
        return (
            self.stream_id == newer.stream_id
            and self.author_id == newer.author_id
            and self.reply_to_discord_message_id
            == newer.reply_to_discord_message_id
            and self.should_reply == newer.should_reply
            and self.route_reason == newer.route_reason
            and self.reply_mode == newer.reply_mode
        )

    def merged_with(self, newer: "PipelineTurn") -> "PipelineTurn":
        if not self.can_merge(newer):
            raise ValueError("incompatible turns cannot be merged")
        return PipelineTurn(
            stream_id=self.stream_id,
            author_id=self.author_id,
            content=f"{self.content}\n{newer.content}",
            source_user_message_ids=(
                *self.source_user_message_ids,
                *newer.source_user_message_ids,
            ),
            should_reply=self.should_reply,
            route_reason=self.route_reason,
            reply_mode=self.reply_mode,
            reply_to_discord_message_id=self.reply_to_discord_message_id,
        )


@dataclass(frozen=True)
class _PendingTurn:
    turn: PipelineTurn
    generation: int


class TurnBuffer:
    """Short in-memory debounce for already stored, compatible turns."""

    def __init__(self, debounce_seconds: float = TURN_DEBOUNCE_SECONDS):
        if debounce_seconds < 0:
            raise ValueError("debounce_seconds must not be negative")
        self.debounce_seconds = debounce_seconds
        self._pending: Dict[Tuple[object, ...], _PendingTurn] = {}
        self._lock = asyncio.Lock()
        self._generation = 0

    async def push(self, turn: PipelineTurn) -> Optional[PipelineTurn]:
        key = self._key(turn)
        async with self._lock:
            self._generation += 1
            generation = self._generation
            current = self._pending.get(key)
            combined = current.turn.merged_with(turn) if current else turn
            self._pending[key] = _PendingTurn(combined, generation)

        try:
            await asyncio.sleep(self.debounce_seconds)
        except asyncio.CancelledError:
            async with self._lock:
                current = self._pending.get(key)
                if current and current.generation == generation:
                    self._pending.pop(key, None)
            raise

        async with self._lock:
            current = self._pending.get(key)
            if current is None or current.generation != generation:
                return None
            self._pending.pop(key, None)
            return current.turn

    @staticmethod
    def _key(turn: PipelineTurn) -> Tuple[object, ...]:
        return (
            turn.stream_id,
            turn.author_id,
            turn.reply_to_discord_message_id,
            turn.should_reply,
            turn.route_reason,
            turn.reply_mode,
        )
