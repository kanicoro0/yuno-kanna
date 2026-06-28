from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Stream:
    id: int
    kind: str
    discord_channel_id: str
    discord_guild_id: Optional[str]
    created_at: str


@dataclass(frozen=True)
class ConversationMessage:
    id: int
    stream_id: int
    discord_message_id: str
    role: str
    author_id: str
    author_name: str
    content: str
    reply_to_discord_message_id: Optional[str]
    created_at: str
    context_visible: bool = True
    searchable: bool = True
