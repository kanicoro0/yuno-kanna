from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class IncomingMessage:
    discord_message_id: str
    discord_channel_id: str
    discord_guild_id: Optional[str]
    stream_kind: str
    author_id: str
    author_name: str
    author_is_bot: bool
    bot_user_id: str
    mentions_bot: bool
    raw_content: str
    created_at: str
    reply_to_discord_message_id: Optional[str]


@dataclass(frozen=True)
class SentMessage:
    discord_message_id: str
    author_id: str
    author_name: str
    content: str
    created_at: str
