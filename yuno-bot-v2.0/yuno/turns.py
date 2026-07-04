from dataclasses import dataclass
from typing import Optional, Tuple

from yuno.conversation.models import ConversationMessage


@dataclass(frozen=True)
class PipelineTurn:
    """The unit selected for reading after its source messages are stored."""

    stream_id: int
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
