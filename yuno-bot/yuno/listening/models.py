from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ListeningChannel:
    discord_channel_id: str
    discord_guild_id: Optional[str]
    source: str
    created_at: Optional[str] = None


@dataclass(frozen=True)
class ListeningChange:
    changed: bool
    source: Optional[str]
    reason: str
